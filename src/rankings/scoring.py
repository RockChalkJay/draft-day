"""Piece 0: configurable scoring -> a single "points" column.

Consumes the merged player table's columns (``{source_prefix}_<GROUP>_<STAT>``)
and writes one ``points`` column, computed per row from the stats appropriate
to that row's position. Missing columns (e.g. a TE row has no PASSING_* stats,
or a synthetic test frame omits a column entirely) contribute 0 -- never a
KeyError.
"""

from dataclasses import dataclass

import pandas as pd

# The only place position-specific raw column names are hardcoded. Maps a
# (category, stat-key) pair from ScoringConfig to the merged frame's column name
# (sans source prefix). Column names verified against FantasyProsFetcher output:
#   QB/RB/WR/TE carry GROUP_STAT names (PASSING_YDS, RECEIVING_REC, ...).
#   K and DST carry bare names (FG, XPT / SACK, INT, ...).
COLUMN_MAP = {
    "passing": {"yds": "PASSING_YDS", "td": "PASSING_TDS", "int": "PASSING_INTS"},
    "rushing": {"yds": "RUSHING_YDS", "td": "RUSHING_TDS"},
    "receiving": {"rec": "RECEIVING_REC", "yds": "RECEIVING_YDS", "td": "RECEIVING_TDS"},
    "misc": {"fl": "MISC_FL"},
    "kicking": {"fg": "FG", "xp": "XPT"},
    "defense": {
        "sack": "SACK", "int": "INT", "fr": "FR",
        "ff": "FF", "td": "TD", "safety": "SAFETY",
    },
}


@dataclass
class ScoringConfig:
    passing: dict[str, float]
    rushing: dict[str, float]
    receiving: dict[str, float]  # "rec" weight: 0 standard, 0.5 half-PPR, 1.0 PPR
    kicking: dict[str, float]
    defense: dict[str, float]  # linear stats only (sack/int/fr/ff/td/safety)
    misc: dict[str, float]

    def categories(self) -> dict[str, dict[str, float]]:
        return {
            "passing": self.passing,
            "rushing": self.rushing,
            "receiving": self.receiving,
            "kicking": self.kicking,
            "defense": self.defense,
            "misc": self.misc,
        }


def _preset(reception_pts: float) -> ScoringConfig:
    return ScoringConfig(
        passing={"yds": 0.04, "td": 4.0, "int": -2.0},
        rushing={"yds": 0.1, "td": 6.0},
        receiving={"rec": reception_pts, "yds": 0.1, "td": 6.0},
        kicking={"fg": 3.0, "xp": 1.0},
        defense={"sack": 1.0, "int": 2.0, "fr": 2.0, "ff": 1.0, "td": 6.0, "safety": 2.0},
        misc={"fl": -2.0},
    )


PRESETS = {
    "standard": _preset(0.0),
    "half_ppr": _preset(0.5),
    "ppr": _preset(1.0),
}


def calculate_points(
    df: pd.DataFrame,
    scoring: ScoringConfig,
    source_prefix: str = "fantasypros",
) -> pd.DataFrame:
    """Return a copy of ``df`` with a ``points`` column added.

    Vectorized over the whole frame: each (category, stat) weight is applied to
    its column where that column exists. Position-inappropriate stats are NaN in
    the merged frame (outer join) and drop out via ``fillna(0)``, so a TE never
    accrues passing points and a QB never accrues receiving points without any
    per-position branching here.
    """
    df = df.copy()
    points = pd.Series(0.0, index=df.index)
    for category, weights in scoring.categories().items():
        stat_to_col = COLUMN_MAP.get(category, {})
        for stat_key, weight in weights.items():
            raw_col = stat_to_col.get(stat_key)
            if raw_col is None or weight == 0:
                continue
            col = f"{source_prefix}_{raw_col}"
            if col in df.columns:
                points = points + weight * pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    df["points"] = points
    return df
