import pandas as pd

from src.rankings.inflation import calculate_position_budgets
from src.rankings.league_state import LeagueState, RosterSlot, Team


def _board():
    rows = []
    # RB and WR each carry total vorp 300; QB carries 150.
    for i in range(3):
        rows.append({"player_id": f"rb{i}", "position": "RB", "vorp": 100})
        rows.append({"player_id": f"wr{i}", "position": "WR", "vorp": 100})
    for i in range(3):
        rows.append({"player_id": f"qb{i}", "position": "QB", "vorp": 50})
    rows.append({"player_id": "k0", "position": "K", "vorp": 0})
    rows.append({"player_id": "dst0", "position": "DST", "vorp": 0})
    return pd.DataFrame(rows)


def _state(cash, slots, drafted=()):
    # One team carrying all the cash and `slots` empty roster spots.
    roster = [RosterSlot("BENCH") for _ in range(slots)]
    return LeagueState(teams=[Team("t0", cash, roster)], drafted_player_ids=set(drafted))


def test_returns_dollar_pools_keyed_by_position():
    out = calculate_position_budgets(_board(), _state(750, 10))
    assert isinstance(out, dict)
    assert set(out.keys()) == {"RB", "WR", "QB"}


def test_pools_sum_to_discretionary_cash():
    # disc = cash - slots = 750 - 10 = 740; pools partition it exactly.
    out = calculate_position_budgets(_board(), _state(750, 10))
    assert round(sum(out.values()), 6) == 740.0


def test_pools_split_by_original_vorp_share():
    # Original shares: RB 300/750, WR 300/750, QB 150/750 -> 2:2:1.
    out = calculate_position_budgets(_board(), _state(750, 0))  # disc = 750
    assert round(out["RB"], 3) == round(750 * 300 / 750, 3)
    assert round(out["QB"], 3) == round(750 * 150 / 750, 3)
    assert round(out["RB"] / out["QB"], 3) == 2.0


def test_pdm_tilts_cash_toward_demanded_position():
    base = calculate_position_budgets(_board(), _state(750, 0))
    tilted = calculate_position_budgets(_board(), _state(750, 0), pdm_map={"RB": 1.25, "WR": 1.0, "QB": 1.0})
    assert tilted["RB"] > base["RB"]  # RB demand pulls a bigger pool
    assert tilted["WR"] < base["WR"]  # others give some up
    assert round(sum(tilted.values()), 6) == 750.0  # still conserves


def test_uniform_pdm_cancels():
    base = calculate_position_budgets(_board(), _state(750, 0))
    uniform = calculate_position_budgets(_board(), _state(750, 0), pdm_map={"RB": 1.25, "WR": 1.25, "QB": 1.25})
    for pos in base:
        assert round(base[pos], 6) == round(uniform[pos], 6)


def test_discretionary_never_negative():
    # More slots than cash -> disc floored at 0, pools all 0, no error.
    out = calculate_position_budgets(_board(), _state(5, 100))
    assert all(v == 0.0 for v in out.values())


def test_k_dst_absent_from_pools():
    out = calculate_position_budgets(_board(), _state(750, 10))
    assert "K" not in out and "DST" not in out
