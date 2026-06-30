import pandas as pd

from src.rankings.tiers import calculate_tiers_by_cliffs


def _frame(scores):
    return pd.DataFrame({"player_id": [f"p{i}" for i in range(len(scores))], "points": scores})


def test_empty_input():
    out = calculate_tiers_by_cliffs(_frame([]), num_tiers=5)
    assert out.empty
    assert "tier" in out.columns


def test_num_tiers_one_forces_single_tier():
    out = calculate_tiers_by_cliffs(_frame([100, 50, 10, 1]), num_tiers=1)
    assert set(out["tier"]) == {1}


def test_len_le_num_tiers_forces_single_tier():
    # 4 players, 5 requested tiers -> all tier 1.
    out = calculate_tiers_by_cliffs(_frame([100, 80, 60, 40]), num_tiers=5)
    assert set(out["tier"]) == {1}


def test_single_big_gap_lands_break_correctly():
    # gap between 98 and 50 (index 2) is the only large one; 1 break for 2 tiers.
    out = calculate_tiers_by_cliffs(_frame([100, 99, 98, 50, 49, 48]), num_tiers=2)
    tiers = out.sort_values("points", ascending=False)["tier"].tolist()
    assert tiers == [1, 1, 1, 2, 2, 2]


def test_adjacent_biggest_gaps_produce_singleton_tier():
    # gaps: 50 (idx0), 10 (idx1), 1, 1. Two largest at idx0,idx1 -> singleton tiers.
    out = calculate_tiers_by_cliffs(_frame([100, 50, 40, 39, 38]), num_tiers=3)
    tiers = out.sort_values("points", ascending=False)["tier"].tolist()
    assert tiers == [1, 2, 3, 3, 3]


def test_tied_scores_produce_fewer_tiers_not_split_equals():
    # Five identical scores then a drop. Only ONE nonzero gap exists, so despite
    # requesting 5 tiers we get 2 -- and the tied players are never split.
    out = calculate_tiers_by_cliffs(_frame([100, 100, 100, 100, 100, 50]), num_tiers=5)
    tiers = out.sort_values("points", ascending=False)["tier"].tolist()
    assert tiers == [1, 1, 1, 1, 1, 2]
    assert max(tiers) == 2  # fewer tiers than requested


def test_zero_gap_never_selected_as_break():
    # gaps: 0 (between the tied 100s), 1, 1. Requesting 3 tiers wants 2 breaks;
    # both come from the nonzero gaps, never the zero -- so the tied 100s share
    # a tier even though a naive "always take num_tiers-1 breaks" would split them.
    out = calculate_tiers_by_cliffs(_frame([100, 100, 99, 98]), num_tiers=3)
    ranked = out.sort_values("points", ascending=False)
    tiers = ranked["tier"].tolist()
    assert tiers[0] == tiers[1]  # the two 100s stay together
    assert tiers == [1, 1, 2, 3]
