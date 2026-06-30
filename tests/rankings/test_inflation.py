import pandas as pd

from src.rankings.inflation import calculate_inflation_index
from src.rankings.league_state import LeagueState, Team


def _board():
    rows = []
    # RB and WR each carry total vorp 300; QB carries 150.
    for i in range(3):
        rows.append({"player_id": f"rb{i}", "position": "RB", "vorp": 100})
        rows.append({"player_id": f"wr{i}", "position": "WR", "vorp": 100})
    for i in range(3):
        rows.append({"player_id": f"qb{i}", "position": "QB", "vorp": 50})
    # K/DST present but vorp 0.
    rows.append({"player_id": "k0", "position": "K", "vorp": 0})
    rows.append({"player_id": "dst0", "position": "DST", "vorp": 0})
    return pd.DataFrame(rows)


def _state(cash, drafted=()):
    return LeagueState(teams=[Team("t0", cash, [])], drafted_player_ids=set(drafted))


def test_returns_dict_keyed_by_position():
    out = calculate_inflation_index(_board(), _state(750))
    assert isinstance(out, dict)
    assert set(out.keys()) == {"RB", "WR", "QB"}


def test_draft_start_matches_single_global_ratio():
    # Nothing drafted: every position == total_cash / total_vorp.
    # total_vorp = 300 + 300 + 150 = 750; cash 750 -> ratio 1.0 everywhere.
    out = calculate_inflation_index(_board(), _state(750))
    assert round(out["RB"], 6) == 1.0
    assert round(out["WR"], 6) == 1.0
    assert round(out["QB"], 6) == 1.0


def test_differentiated_depletion_raises_that_positions_inflation():
    # Draft away most RB vorp (2 of 3 RBs) but no WR. RB remaining shrinks, so
    # RB inflation must exceed WR inflation -- proving the per-position split.
    out = calculate_inflation_index(_board(), _state(750, drafted=["rb0", "rb1"]))
    assert out["RB"] > out["WR"]


def test_remaining_vorp_zero_maps_to_zero_not_error():
    # Draft all three RBs -> RB remaining vorp 0 -> entry is 0, others unaffected.
    out = calculate_inflation_index(_board(), _state(750, drafted=["rb0", "rb1", "rb2"]))
    assert out["RB"] == 0.0
    assert out["WR"] > 0.0


def test_k_dst_absent_from_map():
    out = calculate_inflation_index(_board(), _state(750))
    assert "K" not in out
    assert "DST" not in out
