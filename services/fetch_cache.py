"""Per-run in-memory HTTP fetch cache."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from urllib.parse import urlsplit, urlunsplit


@dataclass
class FetchRecord:
    """Cached fetch result for a single URL."""

    html: str
    final_url: str
    fetched_at: float


@dataclass
class RunFetchCache:
    """Simple per-run cache with normalization and basic stats."""

    items: dict[str, FetchRecord] = field(default_factory=dict)
    hits: int = 0
    misses: int = 0
    writes: int = 0

    def _key(self, url: str) -> str:
        """Normalize URL into a stable cache key."""
        parts = urlsplit(url.strip())
        normalized_path = parts.path or "/"
        return urlunsplit(
            (parts.scheme.lower(), parts.netloc.lower(), normalized_path, parts.query, "")
        )

    def get(self, url: str) -> FetchRecord | None:
        """Lookup a URL in cache and update hit/miss stats."""
        key = self._key(url)
        record = self.items.get(key)
        if record is None:
            self.misses += 1
            return None
        self.hits += 1
        return record

    def put(self, requested_url: str, final_url: str, html: str) -> None:
        """Store fetch result under requested and final URL keys."""
        record = FetchRecord(html=html, final_url=final_url, fetched_at=time())
        self.items[self._key(requested_url)] = record
        self.items[self._key(final_url)] = record
        self.writes += 1
