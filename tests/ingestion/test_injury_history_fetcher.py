from unittest.mock import patch

import pandas as pd
import polars as pl
import pytest

from src.ingestion.injury_history_fetcher import InjuryHistoryFetcher

SAMPLE_INJURIES = pl.DataFrame(
    {
        "full_name": ["Christian McCaffrey", "Christian McCaffrey", "Christian McCaffrey", "Patrick Mahomes"],
        "team": ["SF", "SF", "SF", "KC"],
        "position": ["RB", "RB", "RB", "QB"],
        "season": [2024, 2024, 2024, 2024],
        "week": [1, 1, 2, 1],
        "report_status": ["Questionable", "Out", "Out", "Questionable"],
        "date_modified": pd.to_datetime(
            [
                "2024-09-04T10:00:00Z",
                "2024-09-05T18:00:00Z",  # later same-week update supersedes the row above
                "2024-09-11T18:00:00Z",
                "2024-09-04T12:00:00Z",
            ]
        ),
    }
)


@pytest.fixture
def fetcher():
    return InjuryHistoryFetcher()


@patch("src.ingestion.injury_history_fetcher.nfl.load_injuries")
def test_fetch_aggregates_weekly_reports_per_player(mock_load, fetcher):
    mock_load.return_value = SAMPLE_INJURIES

    df = fetcher.fetch(seasons=2024)

    cmc = df[df["player_name"] == "Christian McCaffrey"].iloc[0]
    assert cmc["weeks_with_injury_report"] == 2
    assert cmc["weeks_out_or_doubtful"] == 2
    assert cmc["seasons_with_injury_report"] == 1
    assert cmc["team"] == "SF"
    assert cmc["source"] == "nflverse_injuries"


@patch("src.ingestion.injury_history_fetcher.nfl.load_injuries")
def test_fetch_handles_failure(mock_load, fetcher):
    mock_load.side_effect = Exception("network down")

    df = fetcher.fetch()

    assert isinstance(df, pd.DataFrame)
    assert df.empty
