import time

import pandas as pd
import pytest

from src.ingestion.cache import DiskCache


@pytest.fixture
def cache(tmp_path):
    return DiskCache(cache_dir=tmp_path / "cache", ttl_seconds=1)


def test_cache_miss_returns_none(cache):
    assert cache.get("missing-key") is None


def test_cache_set_then_get_round_trips(cache):
    df = pd.DataFrame({"a": [1, 2]})
    cache.set("key", df)

    cached = cache.get("key")

    pd.testing.assert_frame_equal(cached, df)


def test_cache_expires_after_ttl(cache):
    df = pd.DataFrame({"a": [1]})
    cache.set("key", df)

    time.sleep(1.1)

    assert cache.get("key") is None
