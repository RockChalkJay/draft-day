"""Piece 6: final auction worth + static/live orchestration.

The static/live split is the core answer to "some of this is live state, some
isn't": scoring/tiers/VORP compute once per config (``calculate_static_rankings``);
TCM/PDM/inflation/worth recompute on demand after each pick
(``apply_live_valuation``).
"""

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.rankings.inflation import calculate_inflation_index
from src.rankings.league_state import LeagueState
from src.rankings.pdm import calculate_pdm
from src.rankings.replacement import (
    ReplacementConfig,
    calculate_replacement_levels,
    calculate_vorp,
)
from src.rankings.scoring import ScoringConfig, calculate_points
from src.rankings.tcm import calculate_tcm
from src.rankings.tiers import calculate_tiers_by_cliffs


def calculate_final_worth(
    df: pd.DataFrame,
    pdm_map: dict[str, float],
    inflation_map: dict[str, float],
) -> pd.Series:
    """``worth = vorp * inflation * tcm * pdm``, then rounded.

    The $1 floor applies only when ``vorp > 0``; a replacement-level player
    (``vorp == 0``, including all K/DST) is hard-priced at $0. Rounding uses
    ``floor(x + 0.5)`` to match JavaScript ``Math.round`` (round-half-up), not
    Python's banker's rounding.
    """
    pos = df["position"]
    pdm = pos.map(pdm_map).fillna(1.0)
    inflation = pos.map(inflation_map).fillna(0.0)
    tcm = df["tcm"].fillna(1.0) if "tcm" in df.columns else 1.0

    raw = df["vorp"] * inflation * tcm * pdm
    rounded = np.floor(raw + 0.5)
    worth = np.where(df["vorp"] > 0, np.maximum(1.0, rounded), 0.0)
    return pd.Series(worth.astype(int), index=df.index)


@dataclass
class RankingsResult:
    players: pd.DataFrame
    replacement_levels: dict[str, float]
    pdm_map: dict[str, float] | None = None
    inflation_map: dict[str, float] | None = None


def calculate_static_rankings(
    df: pd.DataFrame,
    scoring: ScoringConfig,
    num_teams: int,
    num_tiers: int = 5,
    replacement_config: ReplacementConfig | None = None,
) -> RankingsResult:
    """Steps 0-2: points -> tiers -> vorp. No LeagueState needed; compute once
    per scoring/roster-size config and reuse for the whole draft.

    Owns the per-position loop ``calculate_tiers_by_cliffs`` doesn't do: split by
    position, tier each slice, concat back into one frame with a unified ``tier``
    column before vorp runs. No ``tcm``/``worth`` columns yet -- those are live.
    """
    df = calculate_points(df, scoring)

    tiered_parts = [
        calculate_tiers_by_cliffs(group, num_tiers=num_tiers)
        for _, group in df.groupby("position", sort=False)
    ]
    df = pd.concat(tiered_parts, ignore_index=True)

    config = replacement_config or ReplacementConfig()
    replacement_levels = calculate_replacement_levels(df, num_teams, config)
    df["vorp"] = calculate_vorp(df, replacement_levels)

    return RankingsResult(players=df, replacement_levels=replacement_levels)


def apply_live_valuation(
    static_result: RankingsResult,
    league_state: LeagueState,
) -> RankingsResult:
    """Steps 3-6: tcm -> pdm -> inflation -> worth, layered onto a previously
    computed static result. Call again after every pick (and undo)."""
    df = static_result.players.copy()

    df["tcm"] = calculate_tcm(df, league_state)
    pdm_map = calculate_pdm(df, league_state)
    inflation_map = calculate_inflation_index(df, league_state)
    df["pdm"] = df["position"].map(pdm_map).fillna(1.0)
    df["worth"] = calculate_final_worth(df, pdm_map, inflation_map)

    return RankingsResult(
        players=df,
        replacement_levels=static_result.replacement_levels,
        pdm_map=pdm_map,
        inflation_map=inflation_map,
    )
