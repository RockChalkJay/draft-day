"""Piece 6: final auction worth + static/live orchestration.

The static/live split is the core answer to "some of this is live state, some
isn't": scoring/tiers/VORP compute once per config (``calculate_static_rankings``);
TCM/PDM/inflation/worth recompute on demand after each pick
(``apply_live_valuation``).
"""

from dataclasses import dataclass

import pandas as pd

from src.rankings.inflation import (
    calculate_auction_inflation,
    calculate_draft_phase_decay,
)
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

# K/DST are tracked (bid + ownership) but never priced -- confirmed out of scope
# for suggestions/valuation, so they carry no Value/Price/Bargain ($0).
PRICED_POSITIONS = ("QB", "RB", "WR", "TE")


def calculate_value(
    df: pd.DataFrame,
    budget: float,
    total_slots: int,
    priced_positions: tuple[str, ...] = PRICED_POSITIONS,
) -> pd.Series:
    """Stable salary-cap **Value** (VBD -> dollars): what a player is worth to a
    roster, independent of how the draft is unfolding.

    This is the same method FantasyPros' salary-cap calculator runs on consensus
    projections: reserve $1 per rostered slot, then spread the discretionary money
    (``budget - total_slots``) across positive-VORP priced players by VORP share.
    Sums to ``budget`` over the full drafted pool (the $1 filler/K/DST slots make
    up the rest). K/DST and replacement-level (VORP<=0) players -> $0.
    """
    if "vorp" not in df.columns:
        return pd.Series(0, index=df.index, dtype=int)

    vorp = pd.to_numeric(df["vorp"], errors="coerce").fillna(0.0)
    priced = df["position"].isin(priced_positions) & (vorp > 0)
    vorp_pos = vorp.where(priced, 0.0)
    total_vorp = float(vorp_pos.sum())

    value = pd.Series(0.0, index=df.index)
    if total_vorp > 0:
        discretionary = max(0.0, budget - total_slots)
        value = 1.0 + vorp_pos / total_vorp * discretionary
    return value.where(priced, 0.0).round().clip(lower=0).astype(int)


def calculate_price(
    df: pd.DataFrame,
    inflation: float,
    drafted_player_ids: set[str],
    value_col: str = "value",
    priced_positions: tuple[str, ...] = PRICED_POSITIONS,
) -> pd.Series:
    """Live **Price** (the headline ``worth``): ``1 + (value - 1) * inflation``.

    At draft start (``inflation == 1``) Price equals Value; as the room over/under
    pays, conserving inflation scales the premium so remaining Prices track the
    money left. The $1 base keeps min-bid players at $1. Priced only for undrafted
    skill players with real value (``value >= 1``); K/DST, drafted, and worthless
    players are $0.
    """
    if value_col not in df.columns:
        return pd.Series(0, index=df.index, dtype=int)

    value = pd.to_numeric(df[value_col], errors="coerce").fillna(0.0)
    undrafted = ~df["player_id"].isin(drafted_player_ids)
    priced = undrafted & df["position"].isin(priced_positions) & (value >= 1.0)

    price = 1.0 + (value - 1.0) * inflation
    return price.where(priced, 0.0).round().clip(lower=0).astype(int)


def renormalize_value_to_budget(
    df: pd.DataFrame,
    budget: float,
    total_slots: int,
    priced_positions: tuple[str, ...] = PRICED_POSITIONS,
) -> pd.Series:
    """Rescale the ``value`` column so it satisfies the budget identity
    ``Σ(value - 1) over the expected drafted pool == budget - total_slots``.

    Needed when an external auction-value sheet overrides the computed Value:
    sheet values are calibrated to *their* assumed league (teams/budget/roster),
    not yours, so raw they break the conservation property that makes inflation
    open at exactly 1.0 and Bargain open at 0. Rescaling preserves the sheet's
    relative prices while fitting them to the money actually in your room.

    The expected drafted pool is the ``total_slots`` highest-value rows -- the
    same window ``calculate_auction_inflation`` prices against, so the two stay
    consistent by construction. Scaling is monotone (premium ``value - 1`` is
    multiplied by one positive factor), so board order never changes.
    """
    value = pd.to_numeric(df["value"], errors="coerce").fillna(0.0)
    priced = df["position"].isin(priced_positions) & (value >= 1.0)

    target = budget - total_slots
    window = value.sort_values(ascending=False).head(total_slots)
    current = float((window - 1.0).clip(lower=0).sum())
    if target <= 0 or current <= 0:
        return df["value"]

    scaled = 1.0 + (value - 1.0) * (target / current)
    return scaled.where(priced, 0.0).round().clip(lower=0).astype(int)


@dataclass
class RankingsResult:
    players: pd.DataFrame
    replacement_levels: dict[str, float]
    pdm_map: dict[str, float] | None = None
    inflation: float | None = None  # conserving factor (money in room vs board)
    market_heat: float | None = None  # anticipatory draft-phase decay factor


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

    # Expert tiers take precedence over the computed cliff tiers when present:
    # a rankings-sheet import (tier_override, from data/rankings_tiers.csv)
    # wins over the live-fetched FantasyPros tier, which wins over the computed
    # fallback.
    for source_col in ("fantasypros_ecr_tier", "tier_override"):
        if source_col in df.columns:
            expert = pd.to_numeric(df[source_col], errors="coerce")
            df["tier"] = expert.where(expert.notna() & (expert >= 1), df["tier"])
    df["tier"] = pd.to_numeric(df["tier"], errors="coerce").fillna(1)
    # `tier` is per-position throughout the app: dense-rank within position so
    # each position's best cluster is tier 1. Identity for computed cliff tiers
    # (already 1..k per position); expert sheet tiers are *overall* tiers (a
    # TE's best cluster may sit in overall tier 5), so this re-anchors them to
    # the per-position scale the board, PDM, and a drafting manager think in.
    df["tier"] = df.groupby("position")["tier"].rank(method="dense").astype(int)

    config = replacement_config or ReplacementConfig()
    replacement_levels = calculate_replacement_levels(df, num_teams, config)
    df["vorp"] = calculate_vorp(df, replacement_levels)

    return RankingsResult(players=df, replacement_levels=replacement_levels)


def apply_live_valuation(
    static_result: RankingsResult,
    league_state: LeagueState,
) -> RankingsResult:
    """Live layer: **Value** (stable VBD->$), **Price** (=worth, Value scaled by
    conserving inflation), and **Bargain** (Value - Price). TCM/PDM are still
    computed as analytical signals but don't fold into worth. Call after each pick."""
    df = static_result.players.copy()

    df["tcm"] = calculate_tcm(df, league_state)
    pdm_map = calculate_pdm(df, league_state)
    df["pdm"] = df["position"].map(pdm_map).fillna(1.0)

    budget = league_state.initial_cash()
    total_slots = sum(len(t.roster) for t in league_state.teams)
    df["value"] = calculate_value(df, budget, total_slots)
    # A user-supplied auction-value export (data/auction_values.csv, surfaced as
    # value_override by the pipeline) takes precedence over the computed Value --
    # for priced positions only, so a sheet's $1-2 K/DST rows can't give
    # never-priced positions a value that leaks into inflation's denominator.
    # Sheet values are calibrated to the sheet's assumed league, so the blended
    # column is then renormalized to *this* league's budget; otherwise inflation
    # opens away from 1.0 and every Bargain starts red before a single bid.
    if "value_override" in df.columns:
        ov = pd.to_numeric(df["value_override"], errors="coerce")
        usable = ov.notna() & (ov > 0) & df["position"].isin(PRICED_POSITIONS)
        df["value"] = ov.where(usable, df["value"]).round().clip(lower=0).astype(int)
        df["value"] = renormalize_value_to_budget(df, budget, total_slots)
    inflation = calculate_auction_inflation(df, league_state)
    # Predicted price composes the reactive conserving factor with the
    # anticipatory draft-phase decay: prices sag below sheet value as rosters
    # fill even when nobody has over/underpaid yet.
    market_heat = calculate_draft_phase_decay(league_state)
    df["worth"] = calculate_price(df, inflation * market_heat, league_state.drafted_player_ids)
    # Bargain only meaningful for still-biddable players; drafted/unpriced -> 0.
    df["bargain"] = (df["value"] - df["worth"]).where(df["worth"] > 0, 0).astype(int)

    return RankingsResult(
        players=df,
        replacement_levels=static_result.replacement_levels,
        pdm_map=pdm_map,
        inflation=inflation,
        market_heat=market_heat,
    )
