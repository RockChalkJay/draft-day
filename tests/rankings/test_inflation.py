import pandas as pd

from src.rankings.inflation import (
    PHASE_DECAY,
    calculate_auction_inflation,
    calculate_draft_phase_decay,
)
from src.rankings.league_state import LeagueState, RosterSlot, Team


def _board(values):
    return pd.DataFrame([{"player_id": f"p{i}", "position": "RB", "value": v}
                         for i, v in enumerate(values)])


def _state(cash, slots, drafted=()):
    roster = [RosterSlot("BENCH") for _ in range(slots)]  # empty (remaining) slots
    return LeagueState(teams=[Team("t0", cash, roster)], drafted_player_ids=set(drafted))


def test_inflation_is_one_when_cash_matches_value():
    # Σ(value-1) over top-4 = 49+29+14+4 = 96; cash-slots = 100-4 = 96 -> 1.0.
    assert round(calculate_auction_inflation(_board([50, 30, 15, 5]), _state(100, 4)), 3) == 1.0


def test_less_cash_deflates_board():
    assert calculate_auction_inflation(_board([50, 30, 15, 5]), _state(80, 4)) < 1.0


def test_more_cash_inflates_board():
    assert calculate_auction_inflation(_board([50, 30, 15, 5]), _state(120, 4)) > 1.0


def test_only_top_slots_counted():
    # 6 players but 4 slots -> the two cheap extras don't dilute the denominator.
    assert round(calculate_auction_inflation(_board([50, 30, 15, 5, 3, 2]), _state(100, 4)), 3) == 1.0


def test_drafted_players_excluded():
    # Draft p0 ($50). Undrafted top-3 = 30/15/5 -> Σ(v-1)=47; cash-slots = 50-3 = 47 -> 1.0.
    assert round(calculate_auction_inflation(_board([50, 30, 15, 5]), _state(50, 3, ["p0"])), 3) == 1.0


def test_clamped_low_and_high():
    df = _board([50, 30, 15, 5])
    assert calculate_auction_inflation(df, _state(4, 4)) == 0.5     # no discretionary cash
    assert calculate_auction_inflation(df, _state(500, 4)) == 1.8   # cash dwarfs value


def test_no_slots_returns_one():
    assert calculate_auction_inflation(_board([50, 30]), _state(100, 0)) == 1.0


def test_no_value_premium_returns_one():
    assert calculate_auction_inflation(_board([1, 1, 1]), _state(100, 3)) == 1.0


def test_missing_value_column_returns_one():
    df = pd.DataFrame([{"player_id": "p0", "position": "RB"}])
    assert calculate_auction_inflation(df, _state(100, 4)) == 1.0


# ---- Draft-phase decay: prices sag as rosters fill ---------------------------

def _phase_state(filled, total):
    roster = [RosterSlot("BENCH", player_id=f"p{i}" if i < filled else None) for i in range(total)]
    return LeagueState(teams=[Team("t0", 200.0, roster)])


def test_phase_decay_is_one_at_draft_open():
    # No slots filled -> no decay, so every opening-at-par property is untouched.
    assert calculate_draft_phase_decay(_phase_state(0, 10)) == 1.0


def test_phase_decay_quadratic_in_progress():
    # Quadratic: mild through mid-draft, steep at the end.
    assert calculate_draft_phase_decay(_phase_state(5, 10)) == 1.0 - PHASE_DECAY * 0.25
    assert calculate_draft_phase_decay(_phase_state(10, 10)) == 1.0 - PHASE_DECAY


def test_phase_decay_handles_empty_league():
    assert calculate_draft_phase_decay(LeagueState(teams=[])) == 1.0
