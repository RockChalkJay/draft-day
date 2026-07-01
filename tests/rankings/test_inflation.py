import pandas as pd

from src.rankings.inflation import calculate_market_heat
from src.rankings.league_state import LeagueState, Team


def _board():
    # A $41-ceiling player plus cheaper ones (premium of p0 is exactly $40).
    return pd.DataFrame([
        {"player_id": "p0", "position": "RB", "aav": 41},
        {"player_id": "p1", "position": "RB", "aav": 21},
        {"player_id": "p2", "position": "RB", "aav": 11},
    ])


def _state(remaining_cash, drafted=(), starting=200.0):
    return LeagueState(teams=[Team("t0", remaining_cash, [])],
                       drafted_player_ids=set(drafted), starting_bankroll=starting)


def test_heat_is_one_at_draft_start():
    assert calculate_market_heat(_board(), _state(200)) == 1.0


def test_sticker_price_is_neutral():
    # Paid exactly $41 for the $41 ceiling -> spent 41 premium 40 -> heat 1.0.
    assert calculate_market_heat(_board(), _state(159, ["p0"])) == 1.0


def test_overpay_raises_heat():
    # Paid $61 for a $41 ceiling -> the room is running hot.
    assert calculate_market_heat(_board(), _state(139, ["p0"])) > 1.0


def test_bargain_lowers_heat():
    # Paid $21 for a $41 ceiling -> value is going through.
    assert calculate_market_heat(_board(), _state(179, ["p0"])) < 1.0


def test_heat_is_clamped():
    # Absurd overpay (spent $200 on a $41 player) clamps rather than exploding.
    assert calculate_market_heat(_board(), _state(0, ["p0"])) == 2.0


def test_no_premium_bought_returns_one():
    df = pd.DataFrame([{"player_id": "k", "position": "K", "aav": 1}])
    assert calculate_market_heat(df, _state(150, ["k"])) == 1.0


def test_missing_aav_column_returns_one():
    df = pd.DataFrame([{"player_id": "p0", "position": "RB"}])
    assert calculate_market_heat(df, _state(150, ["p0"])) == 1.0
