from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.ingestion.fantasypros_fetcher import FantasyProsFetcher


@pytest.fixture
def fetcher():
    return FantasyProsFetcher()


def test_parse_player_team_parenthesized_format(fetcher):
    assert fetcher._parse_player_team("Patrick Mahomes (KC)") == ("Patrick Mahomes", "KC")
    assert fetcher._parse_player_team("Christian McCaffrey (SF)  ") == ("Christian McCaffrey", "SF")
    assert fetcher._parse_player_team("San Francisco 49ers (SF)") == ("San Francisco 49ers", "SF")


def test_parse_player_team_trailing_abbreviation_format(fetcher):
    assert fetcher._parse_player_team("Jalen Hurts PHI") == ("Jalen Hurts", "PHI")
    assert fetcher._parse_player_team("Patrick Mahomes KC") == ("Patrick Mahomes", "KC")


def test_parse_player_team_dst_full_name_no_abbreviation(fetcher):
    assert fetcher._parse_player_team("Denver Broncos") == ("Denver Broncos", "DEN")
    assert fetcher._parse_player_team("San Francisco 49ers") == ("San Francisco 49ers", "SF")


def test_parse_player_team_no_team_available(fetcher):
    assert fetcher._parse_player_team("Justin Jefferson") == ("Justin Jefferson", "FA")


def test_parse_player_team_does_not_mistake_name_suffix_for_team(fetcher):
    assert fetcher._parse_player_team("Michael Pittman II") == ("Michael Pittman II", "FA")


@patch("requests.Session.get")
def test_fetch_success(mock_get, fetcher):
    mock_html = """
    <html>
    <body>
        <table id="data">
            <thead>
                <tr>
                    <th>Player</th>
                    <th>Stat1</th>
                    <th>Stat2</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>Patrick Mahomes (KC)</td>
                    <td>10.5</td>
                    <td>20.0</td>
                </tr>
                <tr>
                    <td>Lamar Jackson (BAL)</td>
                    <td>15.0</td>
                    <td>30.0</td>
                </tr>
            </tbody>
        </table>
    </body>
    </html>
    """
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = mock_html
    mock_get.return_value = mock_response

    df = fetcher.fetch("qb")

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    assert df.iloc[0]["player_name"] == "Patrick Mahomes"
    assert df.iloc[0]["team"] == "KC"
    assert df.iloc[0]["position"] == "QB"
    assert df.iloc[0]["source"] == "fantasypros"
    assert df.iloc[0]["Stat1"] == 10.5
    assert df.iloc[1]["player_name"] == "Lamar Jackson"
    assert df.iloc[1]["team"] == "BAL"
    assert "Player" not in df.columns


@patch("requests.Session.get")
def test_fetch_disambiguates_grouped_stat_columns(mock_get, fetcher):
    # QB's real table has a group header row (PASSING/RUSHING colspans) above the
    # leaf row, and PASSING and RUSHING both contain a leaf column named "YDS" --
    # without group-prefixing this collapses into one duplicated "YDS" column.
    mock_html = """
    <html>
    <body>
        <table id="data">
            <thead>
                <tr>
                    <td> </td>
                    <td colspan="2"><b>PASSING</b></td>
                    <td colspan="2"><b>RUSHING</b></td>
                </tr>
                <tr>
                    <th>Player</th>
                    <th>YDS</th>
                    <th>TDS</th>
                    <th>YDS</th>
                    <th>TDS</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>Jalen Hurts PHI</td>
                    <td>3800</td>
                    <td>23</td>
                    <td>600</td>
                    <td>15</td>
                </tr>
            </tbody>
        </table>
    </body>
    </html>
    """
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = mock_html
    mock_get.return_value = mock_response

    df = fetcher.fetch("qb")

    assert not df.columns.duplicated().any()
    assert df.iloc[0]["PASSING_YDS"] == 3800
    assert df.iloc[0]["RUSHING_YDS"] == 600


@patch("requests.Session.get")
def test_fetch_success_current_site_format(mock_get, fetcher):
    # FantasyPros now renders the player cell as an <a> tag plus trailing team
    # text instead of "Name (TEAM)" -- this mirrors the live markup.
    mock_html = """
    <html>
    <body>
        <table id="data">
            <thead>
                <tr>
                    <th>Player</th>
                    <th>Stat1</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td><a class="player-name" href="/nfl/projections/jalen-hurts.php">Jalen Hurts</a> PHI</td>
                    <td>10.5</td>
                </tr>
                <tr>
                    <td><a class="player-name" href="/nfl/projections/denver-defense.php">Denver Broncos</a></td>
                    <td>20.0</td>
                </tr>
            </tbody>
        </table>
    </body>
    </html>
    """
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = mock_html
    mock_get.return_value = mock_response

    df = fetcher.fetch("qb")

    assert df.iloc[0]["player_name"] == "Jalen Hurts"
    assert df.iloc[0]["team"] == "PHI"
    assert df.iloc[1]["player_name"] == "Denver Broncos"
    assert df.iloc[1]["team"] == "DEN"


@patch("requests.Session.get")
def test_fetch_failure(mock_get, fetcher):
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.text = ""
    mock_get.raise_for_status.side_effect = Exception("Not Found")
    mock_get.return_value = mock_response

    df = fetcher.fetch("qb")

    assert isinstance(df, pd.DataFrame)
    assert df.empty


@patch("requests.Session.get")
def test_fetch_no_table(mock_get, fetcher):
    mock_html = """
    <html>
    <body>
        <p>No data here</p>
    </body>
    </html>
    """
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = mock_html
    mock_get.return_value = mock_response

    df = fetcher.fetch("qb")

    assert isinstance(df, pd.DataFrame)
    assert df.empty
