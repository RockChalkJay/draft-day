"""Piece 5: live market-heat signal.

``worth`` is a steep value ceiling anchored to AAV (see valuation.py). This
module supplies the live adjustment: is the room paying above or below those
ceilings? It compares money actually spent to the AAV of the players bought:

    heat = (total_spent - num_drafted) / Σ(aav - 1 over drafted players)

i.e. dollars-of-premium paid divided by dollars-of-premium expected. At draft
start it's 1.0 (nothing bought). If the room is paying over sticker (a hot
draft), heat rises and the remaining ceilings scale up with it; if bargains are
going through, heat drops. Unlike a budget-conserving model this makes no
assumption that every roster slot gets filled -- it only looks at what was
actually spent versus bought.
"""

import pandas as pd

from src.rankings.league_state import LeagueState

HEAT_MIN, HEAT_MAX = 0.5, 2.0


def calculate_market_heat(
    df: pd.DataFrame,
    league_state: LeagueState,
    aav_col: str = "aav",
) -> float:
    """Return the market-heat multiplier (1.0 == paying sticker), clamped to a
    sane band so a single early over/underpay can't swing the board wildly."""
    num_drafted = len(league_state.drafted_player_ids)
    if num_drafted == 0 or aav_col not in df.columns:
        return 1.0

    initial_cash = league_state.initial_cash()
    if initial_cash <= 0:
        return 1.0
    total_spent = initial_cash - league_state.total_remaining_cash()

    drafted = df[df["player_id"].isin(league_state.drafted_player_ids)]
    aav = pd.to_numeric(drafted[aav_col], errors="coerce").fillna(0.0)
    premium_expected = (aav - 1.0).clip(lower=0).sum()
    if premium_expected <= 0:
        return 1.0

    heat = (total_spent - num_drafted) / premium_expected
    return float(min(HEAT_MAX, max(HEAT_MIN, heat)))
