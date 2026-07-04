"""Piece 2: replacement level + VORP (static).

Pure function of (df, num_teams, config) -- no LeagueState dependency, computed
once per scoring/roster-size config. K/DST intentionally absent: they price at
$0 under this design (vorp == 0).
"""

import math
from dataclasses import dataclass

import pandas as pd


@dataclass
class ReplacementConfig:
    qb_starters: int = 1
    rb_starters: int = 2
    wr_starters: int = 2
    te_starters: int = 1
    flex_spots: int = 1  # FLEX slots per team (RB/WR/TE eligible)


# Flex slots are RB/WR/TE-eligible but in practice fill almost entirely from
# RB/WR, so total league flex demand (num_teams * flex_spots) is split evenly
# between RB and WR; TE gets none. At the default 12-team / flex_spots=1 league
# this reproduces the original hardcoded "+ floor(num_teams * 0.5)" exactly:
# floor(12 * 1 / 2) == 6 added to each of RB and WR.
def _flex_share_each(num_teams: int, flex_spots: int) -> int:
    return math.floor(num_teams * flex_spots / 2)


def calculate_replacement_levels(
    df: pd.DataFrame,
    num_teams: int,
    config: ReplacementConfig = ReplacementConfig(),
) -> dict[str, float]:
    """Return ``{"QB": pts, "RB": pts, "WR": pts, "TE": pts}``.

    The replacement index for a position is ``num_teams * starters`` (plus the
    flex share for RB/WR), clamped to ``len(pool) - 1`` so a short pool can't
    index out of bounds. The points of the player at that index is the
    replacement level. Positions with an empty pool are omitted.
    """
    flex_each = _flex_share_each(num_teams, config.flex_spots)
    spec = [
        ("QB", config.qb_starters, 0),
        ("RB", config.rb_starters, flex_each),
        ("WR", config.wr_starters, flex_each),
        ("TE", config.te_starters, 0),
    ]

    levels: dict[str, float] = {}
    for pos, starters, flex in spec:
        pool = df[df["position"] == pos].sort_values("points", ascending=False)
        if pool.empty:
            continue
        idx = min(num_teams * starters + flex, len(pool) - 1)
        levels[pos] = float(pool.iloc[idx]["points"])
    return levels


def calculate_vorp(df: pd.DataFrame, replacement_levels: dict[str, float]) -> pd.Series:
    """``max(0, points - replacement_levels[pos])`` for QB/RB/WR/TE; 0 for any
    position absent from ``replacement_levels`` (i.e. K/DST)."""
    rep = df["position"].map(replacement_levels)
    vorp = (df["points"] - rep).clip(lower=0.0)
    return vorp.where(rep.notna(), 0.0)
