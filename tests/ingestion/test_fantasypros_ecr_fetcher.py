from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.ingestion.fantasypros_ecr_fetcher import FantasyProsECRFetcher

SAMPLE_HTML = """
<html><head></head><body>
<script>
var ecrData = {"sport":"NFL","type":"Draft","total_experts":51,"players":[
{"player_id":23133,"player_name":"Bijan Robinson","player_team_id":"ATL","player_position_id":"RB","player_bye_week":"11","rank_ecr":1,"rank_min":"1","rank_max":"5","rank_ave":"2.18","rank_std":"1.14","pos_rank":"RB1","tier":1},
{"player_id":8120,"player_name":"Houston Texans","player_team_id":"HOU","player_position_id":"DST","player_bye_week":"8","rank_ecr":155,"rank_min":"150","rank_max":"171","rank_ave":"151.98","rank_std":"4.92","pos_rank":"DST1","tier":9}
]};
</script>
</body></html>
"""


@pytest.fixture
def fetcher():
    return FantasyProsECRFetcher()


@patch("requests.Session.get")
def test_fetch_parses_embedded_ecr_json(mock_get, fetcher):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = SAMPLE_HTML
    mock_get.return_value = mock_response

    df = fetcher.fetch()

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2

    bijan = df[df["player_name"] == "Bijan Robinson"].iloc[0]
    assert bijan["team"] == "ATL"
    assert bijan["position"] == "RB"
    assert bijan["rank_ecr"] == 1
    assert bijan["pos_rank"] == "RB1"
    assert bijan["rank_std"] == 1.14
    assert bijan["tier"] == 1
    assert bijan["bye"] == 11
    assert bijan["total_experts"] == 51
    assert bijan["source"] == "fantasypros_ecr"

    dst = df[df["player_name"] == "Houston Texans"].iloc[0]
    assert dst["team"] == "HOU"
    assert dst["position"] == "DST"


@patch("requests.Session.get")
def test_fetch_returns_empty_when_ecr_data_missing(mock_get, fetcher):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "<html><body>no data here</body></html>"
    mock_get.return_value = mock_response

    df = fetcher.fetch()

    assert isinstance(df, pd.DataFrame)
    assert df.empty


@patch("requests.Session.get")
def test_fetch_handles_request_failure(mock_get, fetcher):
    mock_get.side_effect = Exception("network down")

    df = fetcher.fetch()

    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_extract_ecr_json_handles_nested_braces(fetcher):
    html = 'var ecrData = {"a": {"b": 1}, "c": [1,2,3]}; var other = {};'
    extracted = fetcher._extract_ecr_json(html)
    assert extracted == '{"a": {"b": 1}, "c": [1,2,3]}'
