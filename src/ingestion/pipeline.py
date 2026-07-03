"""Orchestration: build the one wide merged player table the rankings engine
consumes.

Wires the per-source player-level fetchers through ``merge_sources``, joins the
team-level Vegas source by ``team``, derives the board's context stats (target
share, injury risk, team total), and caches the result to parquet. When live
fetching is unavailable (no network, a source down) it falls back to the bundled
offline sample so the app is always demoable.
"""

import datetime
import json
import os

import numpy as np
import pandas as pd

from src.ingestion.fantasypros_ecr_fetcher import FantasyProsECRFetcher
from src.ingestion.fantasypros_fetcher import FantasyProsFetcher
from src.ingestion.ffc_fetcher import FFCFetcher
from src.ingestion.injury_history_fetcher import InjuryHistoryFetcher
from src.ingestion.merge import merge_sources
from src.ingestion.nflverse_fetcher import NflverseFetcher
from src.ingestion.sleeper_fetcher import SleeperFetcher
from src.ingestion.vegas_fetcher import VegasFetcher

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", ".."))
DATA_DIR = os.path.join(_REPO_ROOT, "data")
CACHE_PATH = os.path.join(DATA_DIR, "players_raw.parquet")
SAMPLE_PATH = os.path.join(DATA_DIR, "sample_players.json")
OVERRIDE_PATH = os.path.join(DATA_DIR, "auction_values.csv")

POSITIONS = ("qb", "rb", "wr", "te", "k", "dst")


def load_sample() -> pd.DataFrame:
    """The bundled offline dataset (raw merged-table shape)."""
    with open(SAMPLE_PATH) as f:
        return pd.DataFrame(json.load(f))


def _recent_seasons(n: int = 1) -> list[int]:
    """The ``n`` most recent *completed* NFL seasons. The current calendar year's
    season hasn't been played at draft time, so the latest completed is last year."""
    latest = datetime.date.today().year - 1
    return list(range(latest - n + 1, latest + 1))


def _num(df: pd.DataFrame, col: str) -> pd.Series:
    return pd.to_numeric(df[col], errors="coerce") if col in df.columns else pd.Series(np.nan, index=df.index)


def _injury_risk(df: pd.DataFrame) -> pd.Series:
    """Low/Med/High from weeks marked Out/Doubtful per season of injury history.
    Blank when there's no history on record (durable veteran or rookie/no data)."""
    per_season = _num(df, "nflverse_injuries_weeks_out_or_doubtful") / _num(
        df, "nflverse_injuries_seasons_with_injury_report"
    ).replace(0, np.nan)
    risk = pd.Series("", index=df.index)
    risk[per_season.notna() & (per_season < 1.0)] = "Low"
    risk[(per_season >= 1.0) & (per_season < 3.0)] = "Med"
    risk[per_season >= 3.0] = "High"
    return risk


def _join_vegas(df: pd.DataFrame, seasons=None) -> pd.DataFrame:
    """Left-join the team-level Vegas implied total onto the player table by team."""
    try:
        v = VegasFetcher().fetch(seasons=seasons)
    except Exception:
        v = pd.DataFrame()
    if v is None or v.empty or "team" not in df.columns:
        return df
    tmap = dict(zip(v["team"], pd.to_numeric(v["vegas_implied_team_total"], errors="coerce")))
    df = df.copy()
    df["vegas_implied_team_total"] = df["team"].map(tmap)
    return df


def _derive_context_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Flatten the raw source columns into the board's display fields."""
    df = df.copy()
    if "nflverse_target_share" in df.columns:
        df["target_share"] = pd.to_numeric(df["nflverse_target_share"], errors="coerce")
    if "vegas_implied_team_total" in df.columns:
        df["team_total"] = pd.to_numeric(df["vegas_implied_team_total"], errors="coerce")
    df["injury_risk"] = _injury_risk(df)
    return df


def _apply_value_override(df: pd.DataFrame) -> pd.DataFrame:
    """If ``data/auction_values.csv`` exists (a user's Draft Wizard export), add a
    ``value_override`` column matched by normalized player name. The rankings
    engine uses it in place of the computed Value. Columns: player + value (also
    accepts name/player_name and salary/auction/aav)."""
    if df.empty or not os.path.exists(OVERRIDE_PATH):
        return df
    try:
        ov = pd.read_csv(OVERRIDE_PATH)
    except Exception:
        return df
    from src.ingestion.id_mapping import normalize_name

    cols = {c.lower(): c for c in ov.columns}
    name_col = cols.get("player") or cols.get("player_name") or cols.get("name")
    val_col = cols.get("value") or cols.get("salary") or cols.get("auction") or cols.get("aav")
    if not name_col or not val_col or "player_name" not in df.columns:
        return df

    vmap = {
        normalize_name(str(n)): v
        for n, v in zip(ov[name_col], pd.to_numeric(ov[val_col], errors="coerce"))
        if pd.notna(v)
    }
    df = df.copy()
    df["value_override"] = df["player_name"].map(lambda n: vmap.get(normalize_name(str(n))))
    return df


def _left_join_by_player(df: pd.DataFrame, other: pd.DataFrame, cols: list[str], prefix: str) -> pd.DataFrame:
    """Left-join selected columns from an enrichment source onto the core table by
    canonical player id. Enrichment sources (nflverse stats, injury history) add
    columns to *existing* players without expanding the universe with the ~2000
    non-fantasy players (defenders, practice squad) they also carry."""
    from src.ingestion.id_mapping import canonical_player_id

    if other is None or other.empty or "player_name" not in other or "position" not in other:
        return df
    keep = [c for c in cols if c in other.columns]
    if not keep:
        return df
    o = other.dropna(subset=["player_name", "position"]).copy()
    o["_pid"] = [canonical_player_id(n, p) for n, p in zip(o["player_name"], o["position"])]
    o = o.drop_duplicates("_pid").set_index("_pid")[keep]
    o.columns = [f"{prefix}{c}" for c in keep]
    return df.join(o, on="player_id")


def fetch_live(scoring_format: str = "ppr") -> pd.DataFrame:
    """Build the core player table from the ECR/projection/ADP sources, then
    enrich it with nflverse usage, injury history, and Vegas team totals. Each
    fetch is failure-tolerant, so a partial outage degrades gracefully."""
    frames = []

    # FantasyPros projections come back one frame per position, all tagged with
    # the same "fantasypros" source. merge_sources keys columns by source name,
    # so the six frames must be concatenated into one first -- otherwise their
    # identically-prefixed stat columns collide ("Indexes have overlapping
    # values"). A row-wise concat unions the differing per-position columns.
    fp = FantasyProsFetcher()
    fp_frames = [f for f in (fp.fetch(pos) for pos in POSITIONS) if f is not None and not f.empty]
    if fp_frames:
        frames.append(pd.concat(fp_frames, ignore_index=True))

    frames.append(FantasyProsECRFetcher().fetch(scoring_format=scoring_format))
    frames.append(FFCFetcher().fetch(scoring_format=scoring_format))
    frames.append(SleeperFetcher().fetch())

    merged = merge_sources([f for f in frames if f is not None and not f.empty])
    if merged.empty:
        return merged

    # Enrichment: left-joined onto the core universe (not merged into it), so
    # these sources add columns without adding non-fantasy players. Prior-season
    # usage; multi-season injury history.
    stat_seasons = _recent_seasons(1)
    try:
        merged = _left_join_by_player(
            merged, NflverseFetcher().fetch(seasons=stat_seasons),
            ["target_share", "air_yards_share", "wopr"], "nflverse_")
    except Exception:
        pass
    try:
        merged = _left_join_by_player(
            merged, InjuryHistoryFetcher().fetch(seasons=_recent_seasons(3)),
            ["weeks_with_injury_report", "weeks_out_or_doubtful", "seasons_with_injury_report"],
            "nflverse_injuries_")
    except Exception:
        pass
    merged = _join_vegas(merged, seasons=stat_seasons)
    merged = _derive_context_stats(merged)
    return merged


def _resolve_table(
    refresh: bool,
    scoring_format: str,
    use_sample_on_failure: bool,
) -> tuple[pd.DataFrame, str]:
    # Offline mode (DRAFTDAY_OFFLINE=1) is deterministic: always the bundled
    # sample, ignoring any cached live pull. Checked before the cache so a
    # previously-fetched real cache can't leak into an offline/test run.
    if os.environ.get("DRAFTDAY_OFFLINE", "").lower() in ("1", "true", "yes"):
        return load_sample(), "sample"

    if not refresh and os.path.exists(CACHE_PATH):
        try:
            return pd.read_parquet(CACHE_PATH), "cache"
        except Exception:
            pass  # corrupt cache -> fall through to a fresh build

    try:
        live = fetch_live(scoring_format=scoring_format)
    except Exception:
        live = pd.DataFrame()

    if not live.empty:
        _write_cache(live)
        return live, "live"

    if use_sample_on_failure:
        return load_sample(), "sample"
    return pd.DataFrame(), "empty"


def load_player_table_with_source(
    refresh: bool = False,
    scoring_format: str = "ppr",
    use_sample_on_failure: bool = True,
) -> tuple[pd.DataFrame, str]:
    """Resolve the merged player table and report where it came from.

    Order of preference: offline sample (if DRAFTDAY_OFFLINE), then the parquet
    cache (unless ``refresh``), then a live fetch, then the bundled sample.
    ``source`` is one of "cache", "live", "sample", or "empty". Any optional
    ``auction_values.csv`` override is applied last, regardless of source.
    """
    df, source = _resolve_table(refresh, scoring_format, use_sample_on_failure)
    return _apply_value_override(df), source


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
