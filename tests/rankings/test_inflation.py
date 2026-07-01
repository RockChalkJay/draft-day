import pandas as pd

from src.rankings.inflation import calculate_auction_inflation
from src.rankings.league_state import LeagueState, RosterSlot, Team


def _board(aavs, pos="RB"):
    return pd.DataFrame([{"player_id": f"p{i}", "position": pos, "aav": a} for i, a in enumerate(aavs)])


def _state(cash, slots, drafted=()):
    roster = [RosterSlot("BENCH") for _ in range(slots)]
    return LeagueState(teams=[Team("t0", cash, roster)], drafted_player_ids=set(drafted))


def test_inflation_is_one_when_market_matches_cash():
    # Σ(aav-1) over top-4 = 49+29+14+4 = 96; disc = 100-4 = 96 -> 1.0.
    df = _board([50, 30, 15, 5])
    assert round(calculate_auction_inflation(df, _state(100, 4)), 3) == 1.0


def test_inflation_rises_when_cash_exceeds_market():
    df = _board([50, 30, 15, 5])
    assert calculate_auction_inflation(df, _state(150, 4)) > 1.0


def test_inflation_falls_when_market_exceeds_cash():
    df = _board([50, 30, 15, 5])
    assert calculate_auction_inflation(df, _state(60, 4)) < 1.0


def test_only_top_slots_counted_in_denominator():
    # 6 players but only 4 slots: the two cheap extras don't dilute inflation.
    df = _board([50, 30, 15, 5, 3, 2])
    assert round(calculate_auction_inflation(df, _state(100, 4)), 3) == 1.0


def test_drafted_players_excluded():
    # Draft p0 ($50). Undrafted top-3 = 30/15/5 -> value 47; disc = 50-3 = 47 -> 1.0.
    df = _board([50, 30, 15, 5])
    assert round(calculate_auction_inflation(df, _state(50, 3, drafted=["p0"])), 3) == 1.0


def test_no_slots_returns_one():
    assert calculate_auction_inflation(_board([50, 30]), _state(100, 0)) == 1.0


def test_no_market_value_returns_one():
    # Everyone at $1 -> no premium to inflate.
    assert calculate_auction_inflation(_board([1, 1, 1]), _state(100, 3)) == 1.0


def test_missing_aav_column_returns_one():
    df = pd.DataFrame([{"player_id": "p0", "position": "RB"}])
    assert calculate_auction_inflation(df, _state(100, 4)) == 1.0
