"""Piece 6: final auction worth + static/live orchestration.

The static/live split is the core answer to "some of this is live state, some
isn't": scoring/tiers/VORP compute once per config (``calculate_static_rankings``);
TCM/PDM/inflation/worth recompute on demand after each pick
(``apply_live_valuation``).
"""

from dataclasses import dataclass

import pandas as pd

from src.rankings.inflation import calculate_auction_inflation
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

# K/DST are tracked (bid + ownership) but never priced -- they carry a market
# AAV of ~$1 and were confirmed out of scope for suggestions/valuation.
PRICED_POSITIONS = ("QB", "RB", "WR", "TE")


def calculate_final_worth(
    df: pd.DataFrame,
    inflation: float,
    drafted_player_ids: set[str],
    aav_col: str = "aav",
    priced_positions: tuple[str, ...] = PRICED_POSITIONS,
) -> pd.Series:
    """Market-anchored auction worth: ``worth = 1 + (aav - 1) * inflation``.

    At draft start (``inflation == 1``) worth equals AAV. As money leaves the
    room faster than value, inflation rises and every remaining player costs a
    little over sticker. Priced only for undrafted skill players with a real
    market value (``aav >= 1``); K/DST, already-drafted, and unpriced players
    are $0.
    """
    if aav_col not in df.columns:
        return pd.Series(0, index=df.index, dtype=int)

    aav = pd.to_numeric(df[aav_col], errors="coerce").fillna(0.0)
    undrafted = ~df["player_id"].isin(drafted_player_ids)
    priced = undrafted & df["position"].isin(priced_positions) & (aav >= 1.0)

    worth = 1.0 + (aav - 1.0) * inflation
    return worth.where(priced, 0.0).round().clip(lower=0).astype(int)


@dataclass
class RankingsResult:
    players: pd.DataFrame
    replacement_levels: dict[str, float]
    pdm_map: dict[str, float] | None = None
    inflation: float | None = None


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
    """Live layer: worth from AAV + inflation. TCM/PDM are still computed as
    analytical signals (cliff / positional demand) for display, but no longer
    fold into worth -- AAV already prices scarcity in. Call after every pick."""
    df = static_result.players.copy()

    df["tcm"] = calculate_tcm(df, league_state)
    pdm_map = calculate_pdm(df, league_state)
    df["pdm"] = df["position"].map(pdm_map).fillna(1.0)
    inflation = calculate_auction_inflation(df, league_state)
    df["worth"] = calculate_final_worth(df, inflation, league_state.drafted_player_ids)

    return RankingsResult(
        players=df,
        replacement_levels=static_result.replacement_levels,
        pdm_map=pdm_map,
        inflation=inflation,
    )
