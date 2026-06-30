import pandas as pd

from src.rankings.replacement import (
    ReplacementConfig,
    calculate_replacement_levels,
    calculate_vorp,
)


def _pool(position, n, top=200, step=2):
    return pd.DataFrame(
        [{"player_id": f"{position}{i}", "position": position, "points": top - i * step}
         for i in range(n)]
    )


def test_replacement_index_hand_computed():
    # 12 teams, default config: repRBIdx = 12*2 + floor(12*1/2) = 30.
    df = _pool("RB", 40, top=200, step=1)  # points = 200 - i
    levels = calculate_replacement_levels(df, num_teams=12)
    assert levels["RB"] == 200 - 30  # points at index 30


def test_replacement_qb_index_hand_computed():
    # repQBIdx = 12*1 = 12.
    df = _pool("QB", 30, top=400, step=1)
    levels = calculate_replacement_levels(df, num_teams=12)
    assert levels["QB"] == 400 - 12


def test_replacement_clamps_to_pool_size():
    # QB pool of only 5; raw index 12 clamps to len-1 = 4.
    df = _pool("QB", 5, top=400, step=10)
    levels = calculate_replacement_levels(df, num_teams=12)
    assert levels["QB"] == 400 - 4 * 10  # points at last index


def test_k_dst_absent_from_replacement_levels():
    df = pd.concat([_pool("RB", 40), _pool("K", 10), _pool("DST", 10)], ignore_index=True)
    levels = calculate_replacement_levels(df, num_teams=12)
    assert "K" not in levels
    assert "DST" not in levels


def test_flex_spots_override_changes_index():
    df = _pool("RB", 60, top=300, step=1)
    base = calculate_replacement_levels(df, num_teams=12, config=ReplacementConfig(flex_spots=1))
    more_flex = calculate_replacement_levels(df, num_teams=12, config=ReplacementConfig(flex_spots=2))
    # flex_spots=2 -> floor(12*2/2)=12 flex share; index 24+12=36 vs 24+6=30.
    assert base["RB"] == 300 - 30
    assert more_flex["RB"] == 300 - 36


def test_vorp_floored_at_zero_and_zero_for_k_dst():
    df = pd.DataFrame(
        [
            {"player_id": "rb1", "position": "RB", "points": 250},
            {"player_id": "rb2", "position": "RB", "points": 100},  # below replacement
            {"player_id": "k1", "position": "K", "points": 180},
        ]
    )
    levels = {"RB": 150.0}  # K absent
    vorp = calculate_vorp(df, levels)
    assert vorp.iloc[0] == 100.0  # 250 - 150
    assert vorp.iloc[1] == 0.0  # max(0, 100-150)
    assert vorp.iloc[2] == 0.0  # K not in levels -> 0
