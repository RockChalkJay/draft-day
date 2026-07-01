"""Orchestration: build the one wide merged player table the rankings engine
consumes.

Wires the per-source player-level fetchers through ``merge_sources`` and caches
the result to parquet. When live fetching is unavailable (no network, a source
down) it falls back to the bundled offline sample so the app is always
demoable. The team-level Vegas source is deliberately not part of the player
table (it has a different shape and isn't consumed by the six-piece pipeline).
"""

import json
import os

import numpy as np
import pandas as pd

from src.ingestion.fantasypros_ecr_fetcher import FantasyProsECRFetcher
from src.ingestion.fantasypros_fetcher import FantasyProsFetcher
from src.ingestion.ffc_fetcher import FFCFetcher
from src.ingestion.merge import merge_sources
from src.ingestion.sleeper_fetcher import SleeperFetcher

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", ".."))
DATA_DIR = os.path.join(_REPO_ROOT, "data")
CACHE_PATH = os.path.join(DATA_DIR, "players_raw.parquet")
SAMPLE_PATH = os.path.join(DATA_DIR, "sample_players.json")

POSITIONS = ("qb", "rb", "wr", "te", "k", "dst")


def load_sample() -> pd.DataFrame:
    """The bundled offline dataset (raw merged-table shape)."""
    with open(SAMPLE_PATH) as f:
        return pd.DataFrame(json.load(f))


ECR_RANK_COL = "fantasypros_ecr_rank_ecr"


def ensure_aav(
    df: pd.DataFrame,
    num_teams: int = 12,
    budget: int = 200,
    roster_size: int = 15,
    cutoff: int = 180,
    exponent: float = 1.3,
) -> pd.DataFrame:
    """Guarantee an ``aav`` (Average Auction Value) column.

    If a market AAV feed already populated ``aav`` (the offline sample, or a
    future direct auction-$ source), it's left untouched. Otherwise AAV is
    synthesized from FantasyPros' ECR **consensus rank** -- real market-ranking
    data -- via a decreasing curve normalized so the drafted pool sums to the
    league budget. This is a market-grounded shape (not our own VORP); a direct
    AAV-dollar feed can replace it by writing the ``aav`` column upstream.

    The absolute level barely matters downstream: the live inflation term
    rescales AAV to the cash actually in the room.
    """
    if "aav" in df.columns and pd.to_numeric(df["aav"], errors="coerce").fillna(0).gt(0).any():
        return df

    df = df.copy()
    if ECR_RANK_COL not in df.columns:
        df["aav"] = 0
        return df

    rank = pd.to_numeric(df[ECR_RANK_COL], errors="coerce")
    skill = df["position"].isin(["QB", "RB", "WR", "TE"]) & rank.notna()
    weight = np.power((cutoff - (rank - 1)).clip(lower=0).where(skill, 0), exponent)
    weight_total = float(weight[skill].sum())
    if weight_total <= 0:
        df["aav"] = 0
        return df

    discretionary = num_teams * budget - num_teams * roster_size
    premium = weight / weight_total * discretionary
    df["aav"] = np.where(skill, (1 + premium).round(), 0).astype(int)
    return df


def fetch_live(scoring_format: str = "ppr") -> pd.DataFrame:
    """Pull every player-level source and merge. Each fetcher already returns an
    empty frame on its own failure; merge_sources skips empties, so a partial
    outage degrades gracefully rather than raising."""
    frames = []

    fp = FantasyProsFetcher()
    for pos in POSITIONS:
        frames.append(fp.fetch(pos))

    frames.append(FantasyProsECRFetcher().fetch(scoring_format=scoring_format))
    frames.append(FFCFetcher().fetch(scoring_format=scoring_format))
    frames.append(SleeperFetcher().fetch())

    return merge_sources([f for f in frames if f is not None and not f.empty])


def load_player_table_with_source(
    refresh: bool = False,
    scoring_format: str = "ppr",
    use_sample_on_failure: bool = True,
) -> tuple[pd.DataFrame, str]:
    """Resolve the merged player table and report where it came from.

    Order of preference: parquet cache (unless ``refresh``), then a live fetch,
    then the bundled sample. ``source`` is one of "cache", "live", "sample", or
    "empty".
    """
    if not refresh and os.path.exists(CACHE_PATH):
        try:
            return pd.read_parquet(CACHE_PATH), "cache"
        except Exception:
            pass  # corrupt cache -> fall through to a fresh build

    # Offline mode (DRAFTDAY_OFFLINE=1) skips the network entirely and serves the
    # bundled sample -- used by tests and offline demos so first load is instant
    # instead of waiting on every source to time out.
    if os.environ.get("DRAFTDAY_OFFLINE", "").lower() in ("1", "true", "yes"):
        return load_sample(), "sample"

    try:
        live = fetch_live(scoring_format=scoring_format)
    except Exception:
        live = pd.DataFrame()

    if not live.empty:
        live = ensure_aav(live)
        _write_cache(live)
        return live, "live"

    if use_sample_on_failure:
        return load_sample(), "sample"
    return pd.DataFrame(), "empty"


def build_player_table(
    refresh: bool = False,
    scoring_format: str = "ppr",
    use_sample_on_failure: bool = True,
) -> pd.DataFrame:
    """Convenience wrapper returning just the table (see
    ``load_player_table_with_source``)."""
    df, _ = load_player_table_with_source(refresh, scoring_format, use_sample_on_failure)
    return df


def _write_cache(df: pd.DataFrame) -> None:
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        df.to_parquet(CACHE_PATH, index=False)
    except Exception:
        pass  # caching is best-effort; a write failure must not break the request
