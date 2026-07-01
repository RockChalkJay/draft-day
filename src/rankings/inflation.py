"""Piece 5: live per-position budget allocation.

The money side of ``worth``. Reserves $1 for every remaining roster slot, then
splits the remaining *discretionary* cash across the skill positions. Each
position's share is its **original** (pre-draft) VORP share -- fixed at draft
start -- times its current demand (PDM). Anchoring to the original share is what
lets a position that depletes faster than expected keep its cash and inflate;
the PDM factor tilts money toward whatever is scarce right now. When PDM is
uniform across positions it cancels, leaving the pure original-share split.

Returns the actual dollar pool per position (not a multiplier), so the total of
all pools equals the discretionary cash exactly -- the basis for ``worth`` being
budget-conserving.
"""

import pandas as pd

from src.rankings.league_state import LeagueState


def calculate_position_budgets(
    df: pd.DataFrame,
    league_state: LeagueState,
    pdm_map: dict[str, float] | None = None,
) -> dict[str, float]:
    """Return ``{pos: dollar_pool}`` for positions with positive original VORP
    (QB/RB/WR/TE; K/DST have vorp 0 and are absent).

    ``disc = total_remaining_cash - remaining_slots`` reserves $1 per slot still
    to be filled. Each position's pool is ``disc * (orig_share * pdm) / Σ``.
    """
    original = df.groupby("position")["vorp"].sum()
    positions = [pos for pos, v in original.items() if v > 0]
    total_original = float(original[positions].sum()) if positions else 0.0
    if total_original <= 0:
        return {}

    cash = league_state.total_remaining_cash()
    remaining_slots = sum(league_state.empty_slots_by_pos().values())
    discretionary = max(0.0, cash - remaining_slots)

    weights = {}
    for pos in positions:
        share = float(original[pos]) / total_original
        demand = (pdm_map or {}).get(pos, 1.0)
        weights[pos] = share * demand
    weight_total = sum(weights.values())
    if weight_total <= 0:
        return {pos: 0.0 for pos in positions}

    return {pos: discretionary * w / weight_total for pos, w in weights.items()}
