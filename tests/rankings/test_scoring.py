import pandas as pd

from src.rankings.scoring import PRESETS, ScoringConfig, calculate_points


def _wr_frame():
    return pd.DataFrame(
        [
            {
                "player_id": "wr1",
                "position": "WR",
                "fantasypros_RECEIVING_REC": 100,
                "fantasypros_RECEIVING_YDS": 1400,
                "fantasypros_RECEIVING_TDS": 10,
            }
        ]
    )


def test_ppr_points_hand_computed():
    df = calculate_points(_wr_frame(), PRESETS["ppr"])
    # 100*1.0 + 1400*0.1 + 10*6 = 100 + 140 + 60
    assert df["points"].iloc[0] == 300.0


def test_half_ppr_points_hand_computed():
    df = calculate_points(_wr_frame(), PRESETS["half_ppr"])
    # 100*0.5 + 140 + 60
    assert df["points"].iloc[0] == 250.0


def test_standard_points_hand_computed():
    df = calculate_points(_wr_frame(), PRESETS["standard"])
    # 0 receptions + 140 + 60
    assert df["points"].iloc[0] == 200.0


def test_custom_scoring_override():
    custom = ScoringConfig(
        passing={}, rushing={}, receiving={"rec": 2.0, "yds": 0.1, "td": 6.0},
        kicking={}, defense={}, misc={},
    )
    df = calculate_points(_wr_frame(), custom)
    # 100*2.0 + 140 + 60
    assert df["points"].iloc[0] == 400.0


def test_missing_columns_default_to_zero_no_keyerror():
    # TE row with only receiving columns: passing/rushing weights apply but the
    # columns are absent entirely -> 0 contribution, no KeyError.
    df = pd.DataFrame(
        [{"player_id": "te1", "position": "TE",
          "fantasypros_RECEIVING_REC": 80, "fantasypros_RECEIVING_YDS": 900,
          "fantasypros_RECEIVING_TDS": 7}]
    )
    out = calculate_points(df, PRESETS["ppr"])
    # 80 + 90 + 42, passing/rushing contribute nothing
    assert out["points"].iloc[0] == 80 + 90 + 42


def test_nan_in_stat_column_treated_as_zero():
    # Outer-join merged frames leave position-inappropriate stats as NaN.
    df = pd.DataFrame(
        [{"player_id": "qb1", "position": "QB",
          "fantasypros_PASSING_YDS": 4000, "fantasypros_PASSING_TDS": 30,
          "fantasypros_PASSING_INTS": 10, "fantasypros_RECEIVING_REC": float("nan")}]
    )
    out = calculate_points(df, PRESETS["ppr"])
    # 4000*0.04 + 30*4 + 10*-2 = 160 + 120 - 20, NaN reception -> 0
    assert out["points"].iloc[0] == 260.0
