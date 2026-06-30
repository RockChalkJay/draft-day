"""Piece 4: Positional Demand Multiplier (live).

A league-wide scarcity signal: how many empty slots chase how many elite
(tier<=2) undrafted players at each position. Kept league-wide -- not
personalized to the viewing team -- because ``worth`` is a market-price
predictor and an auction price is set by aggregate demand, not one team's need
(see ``calculate_personal_need`` for the separate, personalized signal).
"""

import pandas as pd

from src.rankings.league_state import LeagueState, Team

PDM_POSITIONS = ("QB", "RB", "WR", "TE")  # K/DST never included


def _scarcity_multiplier(needed: float, avail_elite: int) -> float:
    elite = avail_elite or 0.1  # only substitutes when count is exactly 0; also guards /0
    sr = needed / elite
    if sr > 1.0:
        return min(1.25, 1 + (sr - 1) * 0.1)
    return 1.0


def _elite_counts(df: pd.DataFrame, league_state: LeagueState) -> dict[str, int]:
    undrafted = df[~df["player_id"].isin(league_state.drafted_player_ids)]
    counts = {}
    for pos in PDM_POSITIONS:
        counts[pos] = int(len(undrafted[(undrafted["position"] == pos) & (undrafted["tier"] <= 2)]))
    return counts


def calculate_pdm(df: pd.DataFrame, league_state: LeagueState) -> dict[str, float]:
    """Return ``{pos: multiplier}`` for QB/RB/WR/TE, league-wide demand.

    ``needed`` = league-wide empty slots at the position, plus a third of the
    empty FLEX slots for RB/WR/TE. The multiplier rises with the ratio of need
    to elite supply, capped at 1.25.
    """
    empty = league_state.empty_slots_by_pos()
    elite_counts = _elite_counts(df, league_state)
    flex = empty.get("FLEX", 0)

    result = {}
    for pos in PDM_POSITIONS:
        needed = empty.get(pos, 0) + (flex / 3 if pos in ("RB", "WR", "TE") else 0)
        result[pos] = _scarcity_multiplier(needed, elite_counts[pos])
    return result


def calculate_personal_need(
    df: pd.DataFrame,
    team: Team,
    league_state: LeagueState,
) -> dict[str, float]:
    """Same scarcity-ratio shape as ``calculate_pdm``, but the numerator is one
    team's own empty slots, not the league's.

    This is a separate signal -- "how badly do *you* need this position right
    now" -- meant to be displayed alongside ``worth`` (the UI's "Best Value For
    Your Needs"), never folded into it. Elite supply is still the league-wide
    undrafted count.
    """
    own_empty = team.empty_slot_counts()
    elite_counts = _elite_counts(df, league_state)
    flex = own_empty.get("FLEX", 0)

    result = {}
    for pos in PDM_POSITIONS:
        needed = own_empty.get(pos, 0) + (flex / 3 if pos in ("RB", "WR", "TE") else 0)
        result[pos] = _scarcity_multiplier(needed, elite_counts[pos])
    return result
