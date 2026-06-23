from unittest.mock import patch

import pandas as pd
import polars as pl
import pytest

from src.ingestion.nflverse_fetcher import NflverseFetcher

# Season-level aggregates (summary_level="reg") name the team column
# "recent_team" -- this is the real schema returned by nflreadpy.
SAMPLE_POLARS_DF = pl.DataFrame(
    {
        "player_id": ["00-0023459"],
        "player_name": ["A.Rodgers"],
        "player_display_name": ["Aaron Rodgers"],
        "position": ["QB"],
        "recent_team": ["NYJ"],
        "season": [2024],
        "target_share": [0.0],
        "fantasy_points_ppr": [8.58],
    }
)

# Week-level data (summary_level="week") names the same column "team".
SAMPLE_WEEKLY_POLARS_DF = pl.DataFrame(
    {
        "player_id": ["00-0023459"],
        "player_name": ["A.Rodgers"],
        "player_display_name": ["Aaron Rodgers"],
        "position": ["QB"],
        "team": ["NYJ"],
        "week": [1],
        "target_share": [0.0],
        "fantasy_points_ppr": [8.58],
    }
)


@pytest.fixture
def fetcher():
    return NflverseFetcher()


@patch("src.ingestion.nflverse_fetcher.nfl.load_player_stats")
def test_fetch_normalizes_player_name_and_source(mock_load, fetcher):
    mock_load.return_value = SAMPLE_POLARS_DF

    df = fetcher.fetch(seasons=2024, summary_level="reg")

    assert isinstance(df, pd.DataFrame)
    row = df.iloc[0]
    assert row["player_name"] == "Aaron Rodgers"
    assert row["source"] == "nflverse"
    assert row["target_share"] == 0.0
    assert row["fantasy_points_ppr"] == 8.58
    assert row["team"] == "NYJ"
    assert "recent_team" not in df.columns


@patch("src.ingestion.nflverse_fetcher.nfl.load_player_stats")
def test_fetch_normalizes_weekly_team_column(mock_load, fetcher):
    mock_load.return_value = SAMPLE_WEEKLY_POLARS_DF

    df = fetcher.fetch(seasons=2024, summary_level="week")

    assert df.iloc[0]["team"] == "NYJ"


@patch("src.ingestion.nflverse_fetcher.nfl.load_player_stats")
def test_fetch_passes_through_args(mock_load, fetcher):
    mock_load.return_value = SAMPLE_POLARS_DF

    fetcher.fetch(seasons=2023, summary_level="reg+post")

    mock_load.assert_called_once_with(seasons=2023, summary_level="reg+post")


@patch("src.ingestion.nflverse_fetcher.nfl.load_player_stats")
def test_fetch_handles_failure(mock_load, fetcher):
    mock_load.side_effect = Exception("network down")

    df = fetcher.fetch()

    assert isinstance(df, pd.DataFrame)
    assert df.empty
