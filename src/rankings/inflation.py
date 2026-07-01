"""Piece 5: live auction inflation.

``worth`` is anchored to market Average Auction Value (AAV). AAV is a static
pre-draft number; this module supplies the *live* adjustment. As the draft runs,
prices drift from AAV based on how fast money is leaving the room relative to the
value still on the board:

    inflation = (remaining_cash - remaining_slots) / Σ(aav - 1 over the players
                still expected to be drafted)

Reserving $1 per remaining slot separates the "value" money from the mandatory
$1 buys. At draft start this is 1.0 (nobody has deviated from AAV yet); when a
stud goes for over AAV, money leaves faster than value and inflation rises, so
everyone left costs a little more than their sticker price. It also rescales AAV
to the actual budget -- AAV need only supply the relative shape.
"""

import pandas as pd

from src.rankings.league_state import LeagueState


def calculate_auction_inflation(
    df: pd.DataFrame,
    league_state: LeagueState,
    aav_col: str = "aav",
) -> float:
    """Return the global auction inflation multiplier (1.0 == on-market).

    The denominator sums the AAV premium (``aav - 1``) over the top ``slots``
    undrafted players -- the ones actually expected to be drafted -- so deep $1
    filler never dilutes it. Falls back to 1.0 when there's no value left to
    price (nothing drafted-able, no cash, or no slots).
    """
    if aav_col not in df.columns:
        return 1.0

    undrafted = df[~df["player_id"].isin(league_state.drafted_player_ids)]
    if undrafted.empty:
        return 1.0

    slots = sum(league_state.empty_slots_by_pos().values())
    if slots <= 0:
        return 1.0

    aav = pd.to_numeric(undrafted[aav_col], errors="coerce").fillna(0.0)
    expected_drafted = aav.sort_values(ascending=False).head(slots)
    value = (expected_drafted - 1.0).clip(lower=0).sum()
    if value <= 0:
        return 1.0

    discretionary = league_state.total_remaining_cash() - slots
    return max(0.0, float(discretionary / value))
