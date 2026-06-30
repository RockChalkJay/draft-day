import os

# Force offline mode before the app/pipeline import any network paths, so
# GET /api/players serves the bundled sample instead of attempting live fetches.
os.environ["DRAFTDAY_OFFLINE"] = "1"

import pytest
from fastapi.testclient import TestClient

from src.api.app import app

client = TestClient(app)


@pytest.fixture
def players():
    resp = client.get("/api/players")
    assert resp.status_code == 200
    return resp.json()["players"]


def test_get_players_returns_sample_offline():
    resp = client.get("/api/players")
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] in ("sample", "cache")
    assert body["count"] > 0
    assert len(body["players"]) == body["count"]
    # raw merged-table columns flow through untouched
    assert "fantasypros_ecr_rank_ecr" in body["players"][0]


def test_static_adds_points_tier_vorp(players):
    resp = client.post(
        "/api/rankings/static",
        json={"players": players, "scoring_config": {"preset": "ppr"}, "num_teams": 12, "num_tiers": 5},
    )
    assert resp.status_code == 200
    body = resp.json()
    first = body["players"][0]
    assert "points" in first and "tier" in first and "vorp" in first
    assert set(body["replacement_levels"]).issubset({"QB", "RB", "WR", "TE"})


def test_full_flow_static_then_live_produces_worth(players):
    static = client.post(
        "/api/rankings/static",
        json={"players": players, "scoring_config": {"preset": "ppr"}, "num_teams": 12},
    ).json()

    roster = [{"pos": p} for p in ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "BENCH", "K", "DST"]]
    league_state = {
        "teams": [{"team_id": f"t{i}", "bankroll": 200.0, "roster": roster} for i in range(12)],
        "drafted_player_ids": [],
    }
    resp = client.post(
        "/api/rankings/live",
        json={"static_result": static, "league_state": league_state},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert set(body["pdm_map"]) == {"QB", "RB", "WR", "TE"}
    assert "K" not in body["inflation_map"]

    by_pos = {}
    for p in body["players"]:
        assert "worth" in p and "tcm" in p and "pdm" in p
        by_pos.setdefault(p["position"], []).append(p["worth"])
    # K/DST are tracked but never priced.
    assert all(w == 0 for w in by_pos.get("K", []))
    assert all(w == 0 for w in by_pos.get("DST", []))
    # Top RB/WR carry real positive worth.
    assert max(by_pos["RB"]) > 0 and max(by_pos["WR"]) > 0


def test_drafting_a_player_changes_inflation(players):
    static = client.post(
        "/api/rankings/static",
        json={"players": players, "scoring_config": {"preset": "ppr"}, "num_teams": 12},
    ).json()
    rb_ids = [p["player_id"] for p in static["players"] if p["position"] == "RB"]

    def live(drafted, cash):
        roster = [{"pos": p} for p in ["RB", "WR", "QB", "FLEX"]]
        ls = {"teams": [{"team_id": "t0", "bankroll": cash, "roster": roster}], "drafted_player_ids": drafted}
        return client.post("/api/rankings/live", json={"static_result": static, "league_state": ls}).json()

    start = live([], 200.0)
    # Draft the three best RBs and reduce cash; RB inflation should move.
    after = live(rb_ids[:3], 140.0)
    assert start["inflation_map"]["RB"] != after["inflation_map"]["RB"]


def test_scoring_override_changes_points(players):
    ppr = client.post(
        "/api/rankings/static",
        json={"players": players, "scoring_config": {"preset": "ppr"}, "num_teams": 12},
    ).json()
    std = client.post(
        "/api/rankings/static",
        json={"players": players, "scoring_config": {"preset": "standard"}, "num_teams": 12},
    ).json()

    def wr_points(body):
        wr = [p for p in body["players"] if p["position"] == "WR"]
        return {p["player_name"]: p["points"] for p in wr}

    ppr_pts, std_pts = wr_points(ppr), wr_points(std)
    # PPR adds a point per reception, so every WR scores strictly higher under PPR.
    assert all(ppr_pts[name] > std_pts[name] for name in ppr_pts)
