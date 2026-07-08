import pandas as pd

from src.ingestion.id_mapping import canonical_player_id

ID_COLUMN = "player_id"
IDENTITY_COLUMNS = ["player_name", "team", "position"]


def merge_sources(frames: list) -> pd.DataFrame:
    """
    Combines normalized fetcher outputs (player_name, team, position, source,
    plus source-specific stat columns) into one wide player table keyed by
    player_id. Each source's stat columns are namespaced with its source name
    (e.g. "fantasypros_FPTS") so colliding column names across sources never
    overwrite each other.

    Each source's stat columns are taken from that source's own frame only
    (not a global union of every frame's columns) -- concatenating frames
    with different columns first and slicing afterwards would otherwise give
    every source a NaN-filled copy of every *other* source's columns too,
    re-prefixed under the wrong source name.

    A source column literally named "player_id" would be overwritten by the
    canonical id assigned here; sources with their own id fields should rename
    them before merging (none of the current universe sources carry one).
    """
    tagged = []
    for df in frames:
        if df is None or df.empty:
            continue
        df = df.copy()
        # Plain assignment (not .loc) so a pre-existing player_id column of any
        # dtype is replaced outright by the canonical string ids.
        df[ID_COLUMN] = [
            canonical_player_id(name, pos) for name, pos in zip(df["player_name"], df["position"])
        ]
        tagged.append(df)
    if not tagged:
        return pd.DataFrame()

    identity_all = pd.concat(
        [df[[ID_COLUMN, "source"] + IDENTITY_COLUMNS] for df in tagged], ignore_index=True
    )
    identity = (
        identity_all.sort_values("source")
        .drop_duplicates(subset=[ID_COLUMN], keep="first")
        .set_index(ID_COLUMN)[IDENTITY_COLUMNS]
    )

    per_source_tables = []
    for df in tagged:
        source = df["source"].iloc[0]
        stat_columns = [
            c for c in df.columns if c not in IDENTITY_COLUMNS and c not in (ID_COLUMN, "source")
        ]
        sub = df.set_index(ID_COLUMN)[stat_columns]
        sub = sub[~sub.index.duplicated(keep="first")]
        sub.columns = [f"{source}_{col}" for col in sub.columns]
        per_source_tables.append(sub)

    result = identity.join(per_source_tables, how="outer")
    return result.reset_index()
