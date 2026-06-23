from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.ingestion.ffc_fetcher import FFCFetcher

SUCCESS_PAYLOAD = {
    "status": "Success",
    "meta": {"type": "standard", "teams": 12, "rounds": 15, "total_drafts": 742},
    "players": [
        {
            "player_id": 2434,
            "name": "Christian McCaffrey",
            "position": "RB",
            "team": "SF",
            "adp": 1.2,
            "adp_formatted": "1.01",
            "times_drafted": 110,
            "high": 1,
            "low": 3,
            "stdev": 0.5,
            "bye": 8,
        }
    ],
}

ERROR_PAYLOAD = {"status": "Error", "errors": "No ADP data found."}


@pytest.fixture
def fetcher():
    session = MagicMock()
    response = MagicMock()
    response.json.return_value = SUCCESS_PAYLOAD
    session.get.return_value = response
    return FFCFetcher(session=session)


def test_fetch_normalizes_player_rows(fetcher):
    df = fetcher.fetch(teams=12, year=2024)

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["player_name"] == "Christian McCaffrey"
    assert row["position"] == "RB"
    assert row["team"] == "SF"
    assert row["source"] == "ffc"
    assert row["adp"] == 1.2
    assert row["stdev"] == 0.5


def test_fetch_passes_query_params(fetcher):
    fetcher.fetch(scoring_format="ppr", teams=10, year=2024, position="RB")

    fetcher.session.get.assert_called_once_with(
        "https://fantasyfootballcalculator.com/api/v1/adp/ppr",
        params={"teams": 10, "position": "RB", "year": 2024},
        timeout=15,
    )


def test_fetch_returns_empty_on_error_payload():
    session = MagicMock()
    response = MagicMock()
    response.json.return_value = ERROR_PAYLOAD
    session.get.return_value = response
    fetcher = FFCFetcher(session=session)

    df = fetcher.fetch()

    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_fetch_handles_request_failure():
    session = MagicMock()
    session.get.side_effect = Exception("network down")
    fetcher = FFCFetcher(session=session)

    df = fetcher.fetch()

    assert isinstance(df, pd.DataFrame)
    assert df.empty
