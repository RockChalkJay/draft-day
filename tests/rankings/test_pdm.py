import pandas as pd

from src.rankings.league_state import LeagueState, RosterSlot, Team
from src.rankings.pdm import calculate_pdm, calculate_personal_need


def _board(elite_per_pos):
    """Build an undrafted board with a known count of tier<=2 players per pos."""
    rows = []
    for pos, n_elite in elite_per_pos.items():
        for i in range(n_elite):
            rows.append({"player_id": f"{pos}e{i}", "position": pos, "tier": 1})
        # add some non-elite depth too
        for i in range(3):
            rows.append({"player_id": f"{pos}d{i}", "position": pos, "tier": 4})
    return pd.DataFrame(rows)


def _team(empty_counts):
    roster = []
    for pos, n in empty_counts.items():
        roster.extend(RosterSlot(pos) for _ in range(n))
    return Team("t0", 200.0, roster)


def test_sr_at_or_below_one_gives_multiplier_one():
    df = _board({"RB": 10, "WR": 10, "QB": 10, "TE": 10})
    # 1 empty RB slot, 10 elite RBs -> sr = 0.1 -> 1.0
    ls = LeagueState(teams=[_team({"RB": 1})], drafted_player_ids=set())
    pdm = calculate_pdm(df, ls)
    assert pdm["RB"] == 1.0


def test_cap_at_1_25():
    df = _board({"RB": 1, "WR": 5, "QB": 5, "TE": 5})
    # Many empty RB slots, only 1 elite RB -> sr huge -> capped at 1.25.
    ls = LeagueState(teams=[_team({"RB": 12}) for _ in range(1)], drafted_player_ids=set())
    pdm = calculate_pdm(df, ls)
    assert pdm["RB"] == 1.25


def test_zero_elite_floor_fires():
    df = _board({"RB": 0, "WR": 5, "QB": 5, "TE": 5})
    # 0 elite RB -> elite floored to 0.1; with 1 empty slot sr = 10 -> 1.25 cap.
    ls = LeagueState(teams=[_team({"RB": 1})], drafted_player_ids=set())
    pdm = calculate_pdm(df, ls)
    assert pdm["RB"] == 1.25  # did not raise ZeroDivisionError


def test_flex_adds_third_of_a_slot():
    df = _board({"RB": 4, "WR": 5, "QB": 5, "TE": 5})
    # No direct RB slots, but 3 FLEX -> RB needed = 0 + 3/3 = 1. 4 elite -> sr 0.25 -> 1.0
    ls = LeagueState(teams=[_team({"FLEX": 3})], drafted_player_ids=set())
    pdm = calculate_pdm(df, ls)
    assert pdm["RB"] == 1.0


def test_k_dst_absent_from_map():
    df = _board({"RB": 5, "WR": 5, "QB": 5, "TE": 5})
    ls = LeagueState(teams=[_team({"RB": 1})], drafted_player_ids=set())
    pdm = calculate_pdm(df, ls)
    assert set(pdm.keys()) == {"QB", "RB", "WR", "TE"}


def test_personal_need_uses_one_teams_slots():
    df = _board({"RB": 2, "WR": 5, "QB": 5, "TE": 5})
    my_team = _team({"RB": 6})
    other = _team({"RB": 0})
    ls = LeagueState(teams=[my_team, other], drafted_player_ids=set())
    # Personal need keys off my_team's 6 empty RB slots vs 2 elite -> sr 3 -> 1.2.
    need = calculate_personal_need(df, my_team, ls)
    assert need["RB"] == min(1.25, 1 + (6 / 2 - 1) * 0.1)
