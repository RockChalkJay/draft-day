"""Piece 6: final auction worth + static/live orchestration.

The static/live split is the core answer to "some of this is live state, some
isn't": scoring/tiers/VORP compute once per config (``calculate_static_rankings``);
TCM/PDM/inflation/worth recompute on demand after each pick
(``apply_live_valuation``).
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.rankings.inflation import calculate_position_budgets
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

# VORP-share pricing systematically overprices elite studs relative to how
# auctions actually clear (you can't spend a third of your budget on one player
# and still field a roster). Raising VORP to a sub-1 power compresses the top and
# lifts the middle to match observed bidding. 0.75 lands the top tier around a
# third of a $200 budget, the empirical rule of thumb. Tunable per league.
WORTH_COMPRESSION = 0.75


def calculate_final_worth(
    df: pd.DataFrame,
    position_budgets: dict[str, float],
    drafted_player_ids: set[str],
    compression: float = WORTH_COMPRESSION,
) -> pd.Series:
    """Budget-conserving auction worth.

    Each position's dollar pool (from ``calculate_position_budgets``) is
    distributed across its *undrafted* players with positive VORP, weighted by
    ``vorp**compression * tcm``. Every such player gets a $1 floor plus its share
    of the pool, so the per-position totals sum back to the discretionary cash --
    ``worth`` is a budget partition, not an unbounded markup. Replacement-level
    players (``vorp == 0``, all K/DST) and already-drafted players are $0.
    """
    worth = pd.Series(0.0, index=df.index)
    tcm = df["tcm"].fillna(1.0) if "tcm" in df.columns else pd.Series(1.0, index=df.index)
    undrafted = ~df["player_id"].isin(drafted_player_ids)

    for pos, pool in position_budgets.items():
        mask = undrafted & (df["position"] == pos) & (df["vorp"] > 0)
        if not mask.any():
            continue
        weight = np.power(df.loc[mask, "vorp"], compression) * tcm[mask]
        weight_total = float(weight.sum())
        if weight_total <= 0:
            continue
        worth.loc[mask] = 1.0 + weight / weight_total * pool

    return worth.round().clip(lower=0).astype(int)


@dataclass
class RankingsResult:
    players: pd.DataFrame
    replacement_levels: dict[str, float]
    pdm_map: dict[str, float] | None = None
    position_budgets: dict[str, float] | None = None


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
    compression: float = WORTH_COMPRESSION,
) -> RankingsResult:
    """Steps 3-6: tcm -> pdm -> budgets -> worth, layered onto a previously
    computed static result. Call again after every pick (and undo)."""
    df = static_result.players.copy()

    df["tcm"] = calculate_tcm(df, league_state)
    pdm_map = calculate_pdm(df, league_state)
    position_budgets = calculate_position_budgets(df, league_state, pdm_map)
    df["pdm"] = df["position"].map(pdm_map).fillna(1.0)
    df["worth"] = calculate_final_worth(
        df, position_budgets, league_state.drafted_player_ids, compression
    )

    return RankingsResult(
        players=df,
        replacement_levels=static_result.replacement_levels,
        pdm_map=pdm_map,
        position_budgets=position_budgets,
    )
