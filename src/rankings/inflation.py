"""Piece 5: live auction inflation.

``worth`` (the Price) is a player's stable ``value`` scaled by this live factor.
Inflation is budget-conserving: it compares the money still in the room to the
value still on the board.

    inflation = (remaining_cash - remaining_slots) / Σ(value - 1 over expected picks)

Reserving $1 per remaining slot separates the mandatory min-bids from the
discretionary money. At draft start it's 1.0 (cash and value are both whole). An
early overpay drains cash faster than value leaves the board, so the ratio drops
below 1 and every remaining Price falls with it -- the economically-correct
direction, since the dollars a rival overspent are dollars no longer chasing the
rest of the pool. Bargains push it back above 1.
"""

import pandas as pd

from src.rankings.league_state import LeagueState

INFL_MIN, INFL_MAX = 0.5, 1.8

# Draft-phase price decay: realized auction prices sag below sheet value as the
# draft progresses -- rosters fill, the pool of bidders who still need (and can
# afford) any given player shrinks, and rooms reliably finish with money unspent.
# Conserving inflation alone can't anticipate that (it assumes every remaining
# dollar chases the board); this factor prices it in ahead of time. Quadratic in
# draft progress: near-par through the early/mid draft, steepening into the
# endgame collapse. At full decay prices sit PHASE_DECAY below the conserving
# level (default 20%).
PHASE_DECAY = 0.2


def calculate_draft_phase_decay(league_state: LeagueState) -> float:
    """Return the anticipatory phase multiplier ``1 - PHASE_DECAY * t**2``,
    where ``t`` is the fraction of league roster slots already filled.

    1.0 at draft open (composes cleanly with conserving inflation and keeps
    every opening-at-par property); ``1 - PHASE_DECAY`` when the last slot
    fills. A disciplined room that keeps paying par accumulates surplus cash,
    which pushes conserving inflation above 1 and offsets this decay -- the two
    factors are designed to be multiplied.
    """
    total_slots = sum(len(t.roster) for t in league_state.teams)
    if total_slots <= 0:
        return 1.0
    empty = sum(league_state.empty_slots_by_pos().values())
    t = 1.0 - empty / total_slots
    return 1.0 - PHASE_DECAY * t * t


def calculate_auction_inflation(
    df: pd.DataFrame,
    league_state: LeagueState,
    value_col: str = "value",
) -> float:
    """Return the conserving inflation multiplier (1.0 == on-value), clamped to a
    sane band so a single early over/underpay can't swing the whole board.

    The denominator sums the value premium (``value - 1``) over the top ``slots``
    undrafted players -- the ones actually expected to be drafted -- so deep $0/$1
    filler never dilutes it.
    """
    if value_col not in df.columns:
        return 1.0

    undrafted = df[~df["player_id"].isin(league_state.drafted_player_ids)]
    slots = sum(league_state.empty_slots_by_pos().values())
    if undrafted.empty or slots <= 0:
        return 1.0

    value = pd.to_numeric(undrafted[value_col], errors="coerce").fillna(0.0)
    expected_picks = value.sort_values(ascending=False).head(slots)
    remaining_premium = (expected_picks - 1.0).clip(lower=0).sum()
    if remaining_premium <= 0:
        return 1.0

    discretionary = league_state.total_remaining_cash() - slots
    inflation = discretionary / remaining_premium
    return float(min(INFL_MAX, max(INFL_MIN, inflation)))
