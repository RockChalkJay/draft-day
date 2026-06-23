from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.ingestion.sleeper_fetcher import SleeperFetcher

SAMPLE_PAYLOAD = {
    "4046": {
        "full_name": "Patrick Mahomes",
        "first_name": "Patrick",
        "last_name": "Mahomes",
        "team": "KC",
        "position": "QB",
        "injury_status": None,
        "age": 30,
        "years_exp": 8,
        "status": "Active",
    },
    "7564": {
        "full_name": None,
        "first_name": "Christian",
        "last_name": "McCaffrey",
        "team": "SF",
        "position": "RB",
        "injury_status": "Questionable",
        "age": 28,
        "years_exp": 7,
        "status": "Active",
    },
    "SF": {
        "full_name": None,
        "first_name": None,
        "last_name": None,
        "team": "SF",
        "position": "DEF",
        "injury_status": None,
        "age": None,
        "years_exp": None,
        "status": "Active",
    },
    "9999": {
        "full_name": "Some Coach",
        "first_name": "Some",
        "last_name": "Coach",
        "team": None,
        "position": "OL",
        "injury_status": None,
        "age": 40,
        "years_exp": 10,
        "status": "Active",
    },
}


@pytest.fixture
def fetcher():
    session = MagicMock()
    response = MagicMock()
    response.json.return_value = SAMPLE_PAYLOAD
    session.get.return_value = response
    return SleeperFetcher(session=session)


def test_fetch_normalizes_player_rows(fetcher):
    df = fetcher.fetch()

    assert isinstance(df, pd.DataFrame)
    mahomes = df[df["player_name"] == "Patrick Mahomes"].iloc[0]
    assert mahomes["team"] == "KC"
    assert mahomes["position"] == "QB"
    assert mahomes["source"] == "sleeper"
    assert mahomes["sleeper_player_id"] == "4046"

    mccaffrey = df[df["player_name"] == "Christian McCaffrey"].iloc[0]
    assert mccaffrey["injury_status"] == "Questionable"


def test_fetch_normalizes_def_position_to_dst(fetcher):
    df = fetcher.fetch()

    defense_rows = df[df["position"] == "DST"]
    assert len(defense_rows) == 1
    assert defense_rows.iloc[0]["player_name"] == "SF"


def test_fetch_excludes_non_fantasy_positions(fetcher):
    df = fetcher.fetch()

    assert "Some Coach" not in df["player_name"].values


def test_fetch_handles_request_failure():
    session = MagicMock()
    session.get.side_effect = Exception("network down")
    fetcher = SleeperFetcher(session=session)

    df = fetcher.fetch()

    assert isinstance(df, pd.DataFrame)
    assert df.empty
