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
# Overridable via env var so tests can run hermetically regardless of whether
# a real data/auction_values.csv exists on the machine running them.
OVERRIDE_PATH = os.environ.get(
    "DRAFTDAY_AUCTION_VALUES_PATH", os.path.join(DATA_DIR, "auction_values.csv")
)
# Same, for the rankings/tiers sheet import (fantasypros_rankings_pdf.py output).
RANKINGS_PATH = os.environ.get(
    "DRAFTDAY_RANKINGS_PATH", os.path.join(DATA_DIR, "rankings_tiers.csv")
)

POSITIONS = ("qb", "rb", "wr", "te", "k", "dst")

# How long a cached live pull stays authoritative. Draft-prep data (projections,
# ECR, byes) shifts daily in season-prep and completely between seasons, so a
# stale cache silently serving last year's board is the failure mode to avoid.
# After the TTL the cache demotes to a fallback: a live re-fetch is attempted
# first, and the stale cache is served only if that fails.
CACHE_TTL_HOURS = float(os.environ.get("DRAFTDAY_CACHE_TTL_HOURS", "24"))


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


# nflverse uses different team codes than the FantasyPros/id_mapping convention
# the rest of the pipeline follows (id_mapping.TEAM_NAME_TO_ABBR: LAR, JAC).
# Remapped at the join boundary rather than changing the shared convention.
_NFLVERSE_TO_FP_TEAM = {"LA": "LAR", "JAX": "JAC"}


def _join_vegas(df: pd.DataFrame, seasons=None) -> pd.DataFrame:
    """Left-join the team-level Vegas implied total onto the player table by team."""
    try:
        v = VegasFetcher().fetch(seasons=seasons)
    except Exception:
        v = pd.DataFrame()
    if v is None or v.empty or "team" not in df.columns:
        return df
    teams = v["team"].replace(_NFLVERSE_TO_FP_TEAM)
    tmap = dict(zip(teams, pd.to_numeric(v["vegas_implied_team_total"], errors="coerce")))
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


def _apply_rankings_override(df: pd.DataFrame) -> pd.DataFrame:
    """If ``data/rankings_tiers.csv`` exists (a rankings-sheet import from
    ``fantasypros_rankings_pdf.py``), override the board's ECR rank and bye with
    the sheet's, and add ``tier_override`` (the sheet's expert tier, honored by
    the rankings engine over computed cliff tiers) and ``ecr_vs_adp`` (experts
    vs. market delta). Skill players match by normalized name; DST rows match by
    team abbreviation, since sources disagree on DST naming."""
    if df.empty or not os.path.exists(RANKINGS_PATH):
        return df
    try:
        rk = pd.read_csv(RANKINGS_PATH)
    except Exception:
        return df
    if not {"player", "position", "rank"}.issubset(rk.columns) or "player_name" not in df.columns:
        return df
    from src.ingestion.id_mapping import normalize_name

    rk = rk.copy()
    rk_is_dst = rk["position"].astype(str).str.upper() == "DST"
    rk["_key"] = rk["player"].map(lambda n: normalize_name(str(n)))
    rk.loc[rk_is_dst, "_key"] = "dst:" + rk.loc[rk_is_dst, "team"].astype(str)
    rk = rk.drop_duplicates("_key").set_index("_key")

    df = df.copy()
    df_is_dst = df["position"].astype(str).str.upper() == "DST"
    keys = df["player_name"].map(lambda n: normalize_name(str(n)))
    keys = keys.where(~df_is_dst, "dst:" + df["team"].astype(str))

    def sheet_col(name):
        if name not in rk.columns:
            return pd.Series(np.nan, index=df.index)
        return pd.to_numeric(keys.map(rk[name]), errors="coerce")

    for target, source in (("fantasypros_ecr_rank_ecr", "rank"), ("fantasypros_ecr_bye", "bye")):
        vals = sheet_col(source)
        if target not in df.columns:
            df[target] = np.nan
        df[target] = vals.where(vals.notna(), df[target])
    df["tier_override"] = sheet_col("tier")
    df["ecr_vs_adp"] = sheet_col("ecr_vs_adp")
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


def _cache_is_fresh() -> bool:
    try:
        age_hours = (datetime.datetime.now().timestamp() - os.path.getmtime(CACHE_PATH)) / 3600
        return age_hours < CACHE_TTL_HOURS
    except OSError:
        return False


def _read_cache() -> pd.DataFrame | None:
    if not os.path.exists(CACHE_PATH):
        return None
    try:
        return pd.read_parquet(CACHE_PATH)
    except Exception:
        return None  # corrupt cache -> treat as absent


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

    if not refresh and _cache_is_fresh():
        cached = _read_cache()
        if cached is not None:
            return cached, "cache"

    try:
        live = fetch_live(scoring_format=scoring_format)
    except Exception:
        live = pd.DataFrame()

    if not live.empty:
        _write_cache(live)
        return live, "live"

    # Live failed: a stale cache is still a real merged table -- far better than
    # the bundled sample -- so it outranks the sample as a fallback.
    if not refresh:
        cached = _read_cache()
        if cached is not None:
            return cached, "cache"

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
    ``auction_values.csv`` / ``rankings_tiers.csv`` overrides are applied last,
    regardless of source.
    """
    df, source = _resolve_table(refresh, scoring_format, use_sample_on_failure)
    return _apply_rankings_override(_apply_value_override(df)), source


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
