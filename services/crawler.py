"""Website crawling service skeleton."""

from __future__ import annotations

from collections import deque
from html.parser import HTMLParser
from typing import Any, Callable, List
from urllib.parse import urljoin, urlsplit, urlunsplit

from core.errors import AppValidationError, CrawlError
from services.fetch_cache import RunFetchCache
from services.http_fetcher import shared_http_fetcher

MAX_HTML_BYTES = 2_000_000


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
    max_depth: int = 1,
    max_pages: int = 50,
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
    if max_pages < 0:
        raise AppValidationError(
            "max_pages must be greater than or equal to 0.",
            details={"field": "max_pages", "value": max_pages},
        )
    if max_pages > 200:
        raise AppValidationError(
            "max_pages must be less than or equal to 200.",
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
    queued: set[str] = {normalized_start}
    visited: set[str] = set()
    discovered_urls: list[str] = []

    while queue and len(discovered_urls) < max_pages:
        current_url, depth = queue.popleft()
        queued.discard(current_url)
        if current_url in visited:
            continue

        if progress_callback:
            progress_callback(
                {
                    "stage": "crawling",
                    "message": f"Crawling ({len(discovered_urls)}/{max_pages})...",
                    "current_url": current_url,
                    "current_depth": depth,
                    "crawled_count": len(discovered_urls),
                    "discovered_pages": len(discovered_urls),
                    "queued_count": len(queue),
                    "visited_count": len(visited),
                }
            )

        # Mark as visited exactly once before attempting network fetch.
        visited.add(current_url)

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
        if discovered_url not in discovered_urls:
            discovered_urls.append(discovered_url)
            if progress_callback:
                progress_callback(
                    {
                        "stage": "crawling",
                        "message": f"Crawling ({len(discovered_urls)}/{max_pages})...",
                        "current_url": discovered_url,
                        "current_depth": depth,
                        "crawled_count": len(discovered_urls),
                        "discovered_pages": len(discovered_urls),
                        "queued_count": len(queue),
                        "visited_count": len(visited),
                    }
                )

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

            # Only crawl links under the same canonical host.
            link_host = _normalized_host(normalized_link)
            if not link_host or link_host != canonical_host:
                continue

            # Skip duplicate or already queued links.
            if normalized_link in visited or normalized_link in queued:
                continue

            queue.append((normalized_link, depth + 1))
            queued.add(normalized_link)

    return discovered_urls
