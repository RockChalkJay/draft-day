"""Piece 5: live per-position inflation index.

Per-position, not one global number. Cash is allocated to each position in
proportion to its *original* (pre-draft) VORP share, then divided by that
position's *current* remaining VORP. Anchoring the share to the original
distribution is what lets positions diverge -- if RB depth dries up faster than
its original share predicted, RB inflation rises faster than the rest. At draft
start it reduces to the single global ``cash / total_vorp`` ratio for every
position.
"""

import pandas as pd

from src.rankings.league_state import LeagueState


def calculate_inflation_index(df: pd.DataFrame, league_state: LeagueState) -> dict[str, float]:
    """Return ``{pos: inflation}`` for positions with positive original VORP
    (i.e. QB/RB/WR/TE; K/DST have vorp 0 and are absent, matching PDM).

    A position whose remaining VORP has hit 0 maps to ``0.0`` rather than raising
    -- and that doesn't affect any other position's entry.
    """
    original = df.groupby("position")["vorp"].sum()
    total_original = float(original.sum())
    if total_original <= 0:
        return {}

    remaining_df = df[~df["player_id"].isin(league_state.drafted_player_ids)]
    remaining = remaining_df.groupby("position")["vorp"].sum()
    cash = league_state.total_remaining_cash()

    result: dict[str, float] = {}
    for pos, orig_vorp in original.items():
        if orig_vorp <= 0:
            continue
        share = orig_vorp / total_original
        cash_share = cash * share
        remaining_vorp = float(remaining.get(pos, 0.0))
        result[pos] = cash_share / remaining_vorp if remaining_vorp > 0 else 0.0
    return result
