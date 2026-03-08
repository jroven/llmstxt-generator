"""Website crawling service skeleton."""

from __future__ import annotations

from collections import deque
from html.parser import HTMLParser
import time
from typing import Any, Callable, List
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from core.constants import (
    CRAWL_DENY_PATH_PREFIXES,
    CRAWL_DENY_QUERY_KEYS,
    DEFAULT_MAX_DEPTH,
    DEFAULT_MAX_PAGES,
    JOB_POLL_INTERVAL_MS,
    MAX_DEPTH_CAP,
    MAX_PAGES_CAP,
    PAGINATION_QUERY_KEYS,
)
from core.errors import AppValidationError, CrawlError
from services.fetch_cache import RunFetchCache
from services.http_fetcher import shared_http_fetcher


class _LinkParser(HTMLParser):
    """Minimal HTML parser that extracts href values from anchor tags."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Collect links from <a href="..."> tags."""
        if tag.lower() != "a":
            return

        for attr_name, attr_value in attrs:
            if attr_name.lower() == "href" and attr_value:
                self.links.append(attr_value)


def _normalize_url(url: str) -> str | None:
    """
    Normalize URL for deduplication.

    Returns None for unsupported/invalid URLs.
    """
    lowered_url = url.strip().lower()
    # Ignore non-page link schemes that should never be crawled.
    if lowered_url.startswith(("mailto:", "tel:", "javascript:")):
        return None

    try:
        split = urlsplit(url)
    except ValueError:
        return None

    if split.scheme not in {"http", "https"}:
        return None
    if not split.netloc:
        return None

    # Remove fragment to avoid duplicate pages that differ only by anchors.
    path = split.path or "/"
    return urlunsplit((split.scheme.lower(), split.netloc.lower(), path, split.query, ""))


def _normalized_host(url: str) -> str | None:
    """Normalize host for same-site matching (strip leading www.)."""
    host = (urlsplit(url).hostname or "").strip().lower()
    if not host:
        return None
    if host.startswith("www."):
        return host[4:]
    return host


def _normalize_crawl_identity(url: str) -> str:
    """Normalize crawl identity by removing pagination query parameters."""
    parts = urlsplit(url)
    filtered_query_items = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in PAGINATION_QUERY_KEYS
    ]
    normalized_query = urlencode(filtered_query_items, doseq=True)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, normalized_query, ""))


def _is_denied_url(url: str) -> bool:
    """Return True when URL matches denylisted crawl patterns."""
    parts = urlsplit(url)
    path_lower = (parts.path or "/").lower()
    if any(path_lower.startswith(prefix) for prefix in CRAWL_DENY_PATH_PREFIXES):
        return True

    query_items = parse_qsl(parts.query, keep_blank_values=True)
    query_keys = {key.lower() for key, _ in query_items}
    if any(deny_key in query_keys for deny_key in CRAWL_DENY_QUERY_KEYS):
        return True

    return False


def _fetch_html(
    url: str, fetch_cache: RunFetchCache | None = None
) -> tuple[str, str]:
    """Fetch HTML content and return (html, final_url) after redirects."""
    try:
        return shared_http_fetcher.fetch_html_with_final_url(url, cache=fetch_cache)
    except CrawlError as exc:
        # Keep crawler behavior: non-HTML pages are skipped without hard failure.
        if exc.code == "non_html_content":
            return "", url
        raise


def crawl_site(
    start_url: str,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_pages: int = DEFAULT_MAX_PAGES,
    fetch_cache: RunFetchCache | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> List[str]:
    """
    Crawl a website from a starting URL using configurable depth and page limits.

    Args:
        start_url: Root URL to begin crawling.
        max_depth: Maximum link depth to traverse from the root URL.
        max_pages: Maximum number of pages to include in results.

    Returns:
        A list of discovered URLs.

    Raises:
        AppValidationError: If input URL or limits are invalid.
        CrawlError: If the seed URL cannot be fetched.
    """
    # Validate and normalize starting URL early.
    if max_depth < 0:
        raise AppValidationError(
            "max_depth must be greater than or equal to 0.",
            details={"field": "max_depth", "value": max_depth},
        )
    if max_depth > MAX_DEPTH_CAP:
        raise AppValidationError(
            f"max_depth must be less than or equal to {MAX_DEPTH_CAP}.",
            details={"field": "max_depth", "value": max_depth},
        )
    if max_pages < 0:
        raise AppValidationError(
            "max_pages must be greater than or equal to 0.",
            details={"field": "max_pages", "value": max_pages},
        )
    if max_pages > MAX_PAGES_CAP:
        raise AppValidationError(
            f"max_pages must be less than or equal to {MAX_PAGES_CAP}.",
            details={"field": "max_pages", "value": max_pages},
        )

    normalized_start = _normalize_url(start_url)
    if not normalized_start:
        raise AppValidationError(
            "Invalid URL. Expected an absolute http(s) URL with a valid domain.",
            details={"field": "url", "value": start_url},
        )

    canonical_host = _normalized_host(normalized_start)
    if not canonical_host:
        raise AppValidationError(
            "Invalid URL. Expected an absolute http(s) URL with a valid domain.",
            details={"field": "url", "value": start_url},
        )

    if max_pages == 0:
        return []

    # BFS queue entries: (absolute_url, depth_from_start).
    queue: deque[tuple[str, int]] = deque([(normalized_start, 0)])
    queued_identities: set[str] = {_normalize_crawl_identity(normalized_start)}
    visited_identities: set[str] = set()
    discovered_urls: list[str] = []
    discovered_identities: set[str] = set()
    last_progress_emit = 0.0
    progress_interval_seconds = JOB_POLL_INTERVAL_MS / 1000.0

    def _emit_crawl_progress(current_url: str, depth: int, *, force: bool = False) -> None:
        """Emit crawl progress updates with time-based throttling."""
        nonlocal last_progress_emit
        if not progress_callback:
            return

        now = time.monotonic()
        if not force and (now - last_progress_emit) < progress_interval_seconds:
            return

        last_progress_emit = now
        progress_callback(
            {
                "stage": "crawling",
                "message": f"Crawling ({len(discovered_urls)}/{max_pages})...",
                "current_url": current_url,
                "current_depth": depth,
                "crawled_count": len(discovered_urls),
                "discovered_pages": len(discovered_urls),
                "queued_count": len(queue),
                "visited_count": len(visited_identities),
            }
        )

    while queue and len(discovered_urls) < max_pages:
        current_url, depth = queue.popleft()
        current_identity = _normalize_crawl_identity(current_url)
        queued_identities.discard(current_identity)
        if current_identity in visited_identities:
            continue

        # Routine progress emits are throttled to reduce lock/write churn.
        _emit_crawl_progress(current_url, depth)

        # Mark as visited exactly once before attempting network fetch.
        visited_identities.add(current_identity)

        try:
            html, final_url = _fetch_html(current_url, fetch_cache=fetch_cache)
        except (CrawlError, AppValidationError) as exc:
            # Seed URL failure means we cannot start a crawl and should fail fast.
            if depth == 0 and current_url == normalized_start:
                raise CrawlError(
                    "Could not reach the start URL. Please check the URL and try again.",
                    code="seed_unreachable",
                    details={
                        "url": current_url,
                        "reason": str(exc),
                        "source_code": getattr(exc, "code", ""),
                    },
                ) from exc

            # Non-seed failures are tolerated so crawl can continue.
            continue

        # Canonicalize on final redirected URL and keep host pinned from seed fetch.
        normalized_final_url = _normalize_url(final_url) or current_url
        final_host = _normalized_host(normalized_final_url)
        if not final_host:
            continue

        if depth == 0:
            canonical_host = final_host

        # Skip out-of-site redirects while still allowing non-fatal continuation.
        if final_host != canonical_host:
            continue

        # Record URL only after a successful in-scope fetch.
        discovered_url = normalized_final_url
        if _is_denied_url(discovered_url):
            continue

        discovered_identity = _normalize_crawl_identity(discovered_url)
        if discovered_identity not in discovered_identities:
            discovered_urls.append(discovered_url)
            discovered_identities.add(discovered_identity)
            # New discovered page is a significant state change; emit immediately.
            _emit_crawl_progress(discovered_url, depth, force=True)

        # Respect depth cap: include this URL, but do not expand its links.
        if depth >= max_depth:
            continue

        parser = _LinkParser()
        parser.feed(html)

        for raw_link in parser.links:
            # Convert relative links into absolute URLs based on current page.
            absolute_link = urljoin(normalized_final_url, raw_link)
            normalized_link = _normalize_url(absolute_link)
            if not normalized_link:
                continue
            if _is_denied_url(normalized_link):
                continue
            identity_link = _normalize_crawl_identity(normalized_link)

            # Only crawl links under the same canonical host.
            link_host = _normalized_host(normalized_link)
            if not link_host or link_host != canonical_host:
                continue

            # Skip duplicate or already queued links.
            if identity_link in visited_identities or identity_link in queued_identities:
                continue

            queue.append((normalized_link, depth + 1))
            queued_identities.add(identity_link)

    return discovered_urls
