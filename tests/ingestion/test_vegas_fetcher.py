from unittest.mock import patch

import pandas as pd
import polars as pl
import pytest

from src.ingestion.vegas_fetcher import VegasFetcher

# KC favored by 3 over BAL, total 46 -> KC implied 24.5, BAL implied 21.5.
# IND a 3-point home underdog to HOU, total 49 -> IND implied 23.0, HOU implied 26.0.
SAMPLE_SCHEDULE = pl.DataFrame(
    {
        "home_team": ["KC", "IND"],
        "away_team": ["BAL", "HOU"],
        "spread_line": [3.0, -3.0],
        "total_line": [46.0, 49.0],
    }
)


@pytest.fixture
def fetcher():
    return VegasFetcher()


@patch("src.ingestion.vegas_fetcher.nfl.load_schedules")
def test_fetch_computes_implied_totals_for_home_and_away(mock_load, fetcher):
    mock_load.return_value = SAMPLE_SCHEDULE

    df = fetcher.fetch(seasons=2024)

    by_team = df.set_index("team")["vegas_implied_team_total"]
    assert by_team["KC"] == 24.5
    assert by_team["BAL"] == 21.5
    assert by_team["IND"] == 23.0
    assert by_team["HOU"] == 26.0


@patch("src.ingestion.vegas_fetcher.nfl.load_schedules")
def test_fetch_averages_across_multiple_games_for_same_team(mock_load):
    # KC plays twice: implied totals 24.5 and 30.0 -> average 27.25
    schedule = pl.DataFrame(
        {
            "home_team": ["KC", "KC"],
            "away_team": ["BAL", "LAC"],
            "spread_line": [3.0, 10.0],
            "total_line": [46.0, 50.0],
        }
    )
    mock_load.return_value = schedule

    df = VegasFetcher().fetch(seasons=2024)

    kc_total = df.set_index("team").loc["KC", "vegas_implied_team_total"]
    assert kc_total == 27.25


@patch("src.ingestion.vegas_fetcher.nfl.load_schedules")
def test_fetch_drops_games_without_lines(mock_load, fetcher):
    schedule = pl.DataFrame(
        {
            "home_team": ["KC"],
            "away_team": ["BAL"],
            "spread_line": [None],
            "total_line": [None],
        },
        schema={"home_team": pl.Utf8, "away_team": pl.Utf8, "spread_line": pl.Float64, "total_line": pl.Float64},
    )
    mock_load.return_value = schedule

    df = fetcher.fetch(seasons=2024)

    assert df.empty


@patch("src.ingestion.vegas_fetcher.nfl.load_schedules")
def test_fetch_handles_failure(mock_load, fetcher):
    mock_load.side_effect = Exception("network down")

    df = fetcher.fetch()

    assert isinstance(df, pd.DataFrame)
    assert df.empty
