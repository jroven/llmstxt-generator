from __future__ import annotations

from services.fetch_cache import RunFetchCache


def test_run_fetch_cache_hits_and_misses() -> None:
    cache = RunFetchCache()

    assert cache.get("https://example.com") is None
    assert cache.misses == 1

    cache.put(
        requested_url="https://example.com",
        final_url="https://www.example.com/",
        html="<html>ok</html>",
    )

    assert cache.writes == 1
    assert cache.get("https://example.com") is not None
    assert cache.get("https://www.example.com/") is not None
    assert cache.hits == 2
