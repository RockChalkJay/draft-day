import hashlib
import time
from pathlib import Path

import pandas as pd

DEFAULT_CACHE_DIR = Path(".cache/ingestion")
DEFAULT_TTL_SECONDS = 3600


class DiskCache:
    """
    On-disk cache for fetcher results, keyed by an arbitrary string (typically
    source name + call args). Avoids re-hitting flaky/rate-limited external
    sites on every pipeline run, e.g. while iterating on rankings math during
    a draft prep session.
    """

    def __init__(self, cache_dir=DEFAULT_CACHE_DIR, ttl_seconds=DEFAULT_TTL_SECONDS):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_seconds

    def _path_for(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode()).hexdigest()
        return self.cache_dir / f"{digest}.pkl"

    def get(self, key: str):
        path = self._path_for(key)
        if not path.exists():
            return None
        if time.time() - path.stat().st_mtime > self.ttl_seconds:
            return None
        return pd.read_pickle(path)

    def set(self, key: str, df: pd.DataFrame) -> None:
        df.to_pickle(self._path_for(key))
