import pandas as pd

from src.rankings.league_state import LeagueState
from src.rankings.tcm import calculate_tcm


def _frame(rows):
    return pd.DataFrame(rows)


def _state(drafted=()):
    return LeagueState(teams=[], drafted_player_ids=set(drafted))


def test_drop_over_threshold_triggers_multiplier():
    df = _frame(
        [
            {"player_id": "rb0", "position": "RB", "points": 100},
            {"player_id": "rb1", "position": "RB", "points": 98},
            {"player_id": "rb2", "position": "RB", "points": 96},
            {"player_id": "rb3", "position": "RB", "points": 50},
            {"player_id": "rb4", "position": "RB", "points": 48},
        ]
    )
    tcm = calculate_tcm(df, _state())
    by_id = dict(zip(df["player_id"], tcm))
    # rb0 vs rb2: (100-96)/100 = 0.04 -> no cliff -> 1.0
    assert by_id["rb0"] == 1.0
    # rb1 vs rb3: (98-50)/98 = 0.4898 -> 1 + drop
    assert round(by_id["rb1"], 4) == round(1 + (98 - 50) / 98, 4)
    # rb2 vs rb4: (96-48)/96 = 0.5 -> 1.5
    assert by_id["rb2"] == 1.5


def test_tail_players_get_one():
    df = _frame(
        [
            {"player_id": "rb0", "position": "RB", "points": 100},
            {"player_id": "rb1", "position": "RB", "points": 50},
            {"player_id": "rb2", "position": "RB", "points": 40},
        ]
    )
    tcm = calculate_tcm(df, _state())
    by_id = dict(zip(df["player_id"], tcm))
    # rb1 and rb2 are the last two -> no row two below -> 1.0
    assert by_id["rb1"] == 1.0
    assert by_id["rb2"] == 1.0


def test_zero_points_no_division_error():
    df = _frame(
        [
            {"player_id": "rb0", "position": "RB", "points": 0},
            {"player_id": "rb1", "position": "RB", "points": 0},
            {"player_id": "rb2", "position": "RB", "points": 0},
        ]
    )
    tcm = calculate_tcm(df, _state())
    assert (tcm.dropna() == 1.0).all()


def test_drafted_rows_get_nan():
    df = _frame(
        [
            {"player_id": "rb0", "position": "RB", "points": 100},
            {"player_id": "rb1", "position": "RB", "points": 98},
            {"player_id": "rb2", "position": "RB", "points": 50},
        ]
    )
    tcm = calculate_tcm(df, _state(drafted=["rb1"]))
    by_id = dict(zip(df["player_id"], tcm))
    assert pd.isna(by_id["rb1"])


def test_staleness_regression_gap_opens_after_picks():
    # Pre-draft rb0 has no cliff (next-2 is rb2 at 96, a 4% drop). After rb1 and
    # rb2 are drafted, rb0's real 2-below becomes rb4 (50) -> a 50% cliff appears.
    df = _frame(
        [
            {"player_id": "rb0", "position": "RB", "points": 100},
            {"player_id": "rb1", "position": "RB", "points": 98},
            {"player_id": "rb2", "position": "RB", "points": 96},
            {"player_id": "rb3", "position": "RB", "points": 94},
            {"player_id": "rb4", "position": "RB", "points": 50},
        ]
    )
    pre = dict(zip(df["player_id"], calculate_tcm(df, _state())))
    assert pre["rb0"] == 1.0  # no cliff before the draft

    post = dict(zip(df["player_id"], calculate_tcm(df, _state(drafted=["rb1", "rb2"]))))
    # Undrafted now [100, 94, 50]; rb0 vs 50 = 0.5 drop -> cliff appears.
    assert post["rb0"] == 1.5
