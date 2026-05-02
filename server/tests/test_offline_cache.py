import time

from core.offline_cache import OfflineCache


def test_offline_cache_hit_and_stats():
    cache = OfflineCache(default_ttl_seconds=60, max_entries=2)
    key = cache.build_key("demo", {"prompt": "hello"})
    cache.set(key, {"value": "world"})

    assert cache.get(key) == {"value": "world"}
    stats = cache.get_stats()
    assert stats["hits"] == 1
    assert stats["entries"] == 1


def test_offline_cache_expires_entries():
    cache = OfflineCache(default_ttl_seconds=0, max_entries=2)
    key = cache.build_key("demo", {"prompt": "expire"})
    cache.set(key, {"value": "x"}, ttl_seconds=0)
    time.sleep(0.01)

    assert cache.get(key) is None
    stats = cache.get_stats()
    assert stats["misses"] == 1
