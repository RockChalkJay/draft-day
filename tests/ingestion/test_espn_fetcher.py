import pandas as pd

from src.ingestion.espn_fetcher import EspnFetcher


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, team_payload, players_payload):
        self.headers = {}
        self._team_payload = team_payload
        self._players_payload = players_payload
        self.requests = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.requests.append((url, params, headers))
        if params and params.get("view") == "proTeamSchedules":
            return _FakeResponse(self._team_payload)
        return _FakeResponse(self._players_payload)


def _team_payload():
    return {"settings": {"proTeams": [
        {"id": 6, "abbrev": "DAL"},
        {"id": 28, "abbrev": "WSH"},   # remapped to WAS
        {"id": 30, "abbrev": "JAX"},   # remapped to JAC
    ]}}


def test_fetch_maps_positions_teams_and_ownership_fields():
    players = [
        {"fullName": "CeeDee Lamb", "defaultPositionId": 3, "proTeamId": 6,
         "draftRanksByRankType": {"PPR": {"rank": 5, "auctionValue": 40}},
         "ownership": {"averageDraftPosition": 6.2, "auctionValueAverage": 38.5,
                       "percentOwned": 99.9, "percentStarted": 99.1}},
        {"fullName": "Jayden Daniels", "defaultPositionId": 1, "proTeamId": 28,
         "ownership": {"averageDraftPosition": 20.0}},
        {"fullName": "Some Kicker", "defaultPositionId": 5, "proTeamId": 30},
        {"fullName": "No Position Player", "defaultPositionId": 99, "proTeamId": 6},
    ]
    session = _FakeSession(_team_payload(), players)

    df = EspnFetcher(session=session).fetch(scoring_format="ppr", year=2026)

    assert len(df) == 3  # the unmapped-position row is dropped
    lamb = df.set_index("player_name").loc["CeeDee Lamb"]
    assert lamb["team"] == "DAL" and lamb["position"] == "WR"
    # Bare column names (no self-prefix) -- the pipeline's enrichment join adds
    # the "espn_" prefix; a fetcher-side prefix would double up and vanish.
    assert lamb["adp"] == 6.2 and lamb["auction_value"] == 38.5
    assert lamb["pct_owned"] == 99.9 and lamb["pct_started"] == 99.1

    daniels = df.set_index("player_name").loc["Jayden Daniels"]
    assert daniels["team"] == "WAS"  # WSH remapped
    kicker = df.set_index("player_name").loc["Some Kicker"]
    assert kicker["team"] == "JAC"  # JAX remapped


def test_fetch_uses_rank_auction_value_when_no_live_ownership_average():
    players = [
        {"fullName": "Rookie WR", "defaultPositionId": 3, "proTeamId": 6,
         "draftRanksByRankType": {"PPR": {"rank": 40, "auctionValue": 12}},
         "ownership": {}},
    ]
    session = _FakeSession(_team_payload(), players)

    df = EspnFetcher(session=session).fetch(scoring_format="ppr", year=2026)

    assert df.iloc[0]["auction_value"] == 12
    assert df.iloc[0]["overall_rank"] == 40


def test_fetch_returns_empty_on_request_failure():
    class _FailingSession:
        headers = {}

        def get(self, *a, **k):
            raise RuntimeError("network down")

    df = EspnFetcher(session=_FailingSession()).fetch()
    assert df.empty


def test_fetch_sends_correct_scoring_format_rank_type():
    import json

    players = [{"fullName": "Test Player", "defaultPositionId": 2, "proTeamId": 6, "ownership": {}}]
    session = _FakeSession(_team_payload(), players)

    EspnFetcher(session=session).fetch(scoring_format="standard", year=2026)

    players_request = next(r for r in session.requests if r[1].get("view") == "kona_player_info")
    filt = json.loads(players_request[2]["x-fantasy-filter"])
    assert filt["players"]["sortDraftRanks"]["value"] == "STANDARD"
