"""Piece 1: tiering by cliff detection (static).

Operates on one position's slice at a time -- the caller filters by position
first. The per-position loop and reassembly live in
``valuation.calculate_static_rankings``; this module stays single-position
in / single-position out.
"""

import numpy as np
import pandas as pd


def calculate_tiers_by_cliffs(
    df: pd.DataFrame,
    num_tiers: int = 5,
    score_key: str = "points",
) -> pd.DataFrame:
    """Return ``df`` sorted descending by ``score_key`` with a 1-indexed
    ``tier`` column.

    Tiers are cut at the largest score gaps. Breaks are chosen only from gaps
    strictly > 0, using ``min(num_tiers - 1, count of nonzero gaps)`` of them --
    so two players with identical scores are never split into different tiers
    (a tier is a real drop in score, not an arbitrary split among equals). When
    ``len <= num_tiers`` or ``num_tiers <= 1`` every player lands in tier 1.
    """
    df = df.sort_values(score_key, ascending=False).reset_index(drop=True)
    n = len(df)

    if n == 0:
        df["tier"] = pd.Series([], dtype=int)
        return df

    if n <= num_tiers or num_tiers <= 1:
        df["tier"] = 1
        return df

    scores = df[score_key].to_numpy(dtype=float)
    gaps = scores[:-1] - scores[1:]  # gaps[i] = drop between player i and i+1

    nonzero = [i for i in range(len(gaps)) if gaps[i] > 0]
    k = min(num_tiers - 1, len(nonzero))
    # k largest strictly-positive gaps; ties broken by earlier index for stability.
    chosen = set(sorted(nonzero, key=lambda i: (-gaps[i], i))[:k])

    tiers = np.empty(n, dtype=int)
    current = 1
    for i in range(n):
        tiers[i] = current
        if i in chosen:
            current += 1
    df["tier"] = tiers
    return df
