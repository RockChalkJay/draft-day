from src.rankings.league_state import LeagueState, RosterSlot, Team


def _starter_roster():
    return [
        RosterSlot("QB", "qb1"),
        RosterSlot("RB", "rb1"),
        RosterSlot("RB"),  # empty
        RosterSlot("WR"),  # empty
        RosterSlot("WR"),  # empty
        RosterSlot("TE", "te1"),
        RosterSlot("FLEX"),  # empty
        RosterSlot("BENCH"),  # empty
    ]


def test_team_empty_slot_counts_only_counts_unfilled():
    team = Team("t0", 150.0, _starter_roster())
    counts = team.empty_slot_counts()
    assert counts == {"RB": 1, "WR": 2, "FLEX": 1, "BENCH": 1}
    assert "QB" not in counts  # filled slot omitted


def test_league_state_total_remaining_cash_sums_bankrolls():
    ls = LeagueState(
        teams=[Team("t0", 100.0, []), Team("t1", 75.5, []), Team("t2", 0.0, [])],
        drafted_player_ids=set(),
    )
    assert ls.total_remaining_cash() == 175.5


def test_league_state_empty_slots_by_pos_aggregates_across_teams():
    ls = LeagueState(
        teams=[Team("t0", 100.0, _starter_roster()), Team("t1", 100.0, _starter_roster())],
        drafted_player_ids=set(),
    )
    agg = ls.empty_slots_by_pos()
    assert agg == {"RB": 2, "WR": 4, "FLEX": 2, "BENCH": 2}
