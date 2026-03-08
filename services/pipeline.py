"""Generation pipeline orchestration shared by API and CLI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlsplit

from core.errors import AppError, CrawlError
from core.url_input import build_url_attempts
from schemas import PageMetadata, SiteMetadata
from services.crawler import crawl_site
from services.extractor import extract_page_metadata
from services.fetch_cache import RunFetchCache
from services.generator import generate_llms_txt
from services.http_fetcher import shared_http_fetcher


@dataclass(frozen=True)
class GenerationForUrlResult:
    """Result payload for a single resolved-URL generation run."""

    llms_txt: str
    discovered_count: int
    processed_count: int
    failed_pages: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class GenerationResult:
    """Result payload for generation including resolved source URL."""

    llms_txt: str
    discovered_count: int
    processed_count: int
    source_url: str
    failed_pages: tuple[dict[str, str], ...]


def run_generation_for_url(
    resolved_url: str,
    max_depth: int,
    max_pages: int,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> GenerationForUrlResult:
    """Run crawl -> extract -> generate pipeline for a fully-resolved URL."""
    fetch_cache = RunFetchCache()

    if progress_callback:
        progress_callback({"stage": "crawling", "message": "Crawling site links..."})

    discovered_urls: list[str] = crawl_site(
        resolved_url,
        max_depth=max_depth,
        max_pages=max_pages,
        fetch_cache=fetch_cache,
        progress_callback=progress_callback,
    )

    if progress_callback:
        progress_callback(
            {
                "stage": "extracting",
                "message": "Extracting page metadata...",
                "discovered_pages": len(discovered_urls),
                "processed_pages": 0,
                "failed_count": 0,
            }
        )

    pages: list[PageMetadata] = []
    failed_pages: list[dict[str, str]] = []
    for index, page_url in enumerate(discovered_urls, start=1):
        try:
            html, _ = shared_http_fetcher.fetch_html_with_final_url(page_url, cache=fetch_cache)
            page_metadata = extract_page_metadata(page_url, html)
            pages.append(page_metadata)
        except AppError as exc:
            # Skip individual page failures so one bad page does not abort the run.
            failed_pages.append(
                {
                    "url": page_url,
                    "code": exc.code,
                    "reason": exc.message,
                }
            )
            continue
        finally:
            if progress_callback:
                progress_callback(
                    {
                        "stage": "extracting",
                        "message": f"Extracting metadata ({index}/{len(discovered_urls)})...",
                        "discovered_pages": len(discovered_urls),
                        "processed_pages": len(pages),
                        "failed_count": len(failed_pages),
                    }
                )

    if not pages:
        raise CrawlError(
            "Could not extract metadata from any crawled pages.",
            code="metadata_extraction_failed",
            details={"url": resolved_url},
        )

    # Prefer root page metadata for site-level fields; fallback to URL domain.
    input_domain = urlsplit(resolved_url).netloc or "Site"
    root_page = next(
        (p for p in pages if str(p.url).rstrip("/") == resolved_url.rstrip("/")),
        pages[0],
    )
    inferred_site_title = (root_page.title or "").strip() or input_domain
    inferred_summary = (root_page.description or "").strip() or "Site summary goes here."

    site_metadata = SiteMetadata(
        site_url=resolved_url,
        site_title=inferred_site_title,
        summary=inferred_summary,
    )
    if progress_callback:
        progress_callback({"stage": "generating", "message": "Building llms.txt document..."})
    llms_txt_output = generate_llms_txt(pages, site_metadata)
    return GenerationForUrlResult(
        llms_txt=llms_txt_output,
        discovered_count=len(discovered_urls),
        processed_count=len(pages),
        failed_pages=tuple(failed_pages),
    )


def is_connection_failure(exc: CrawlError) -> bool:
    """Return True when an error indicates network/connectivity failure."""
    if exc.code == "fetch_failed":
        return True
    if exc.code == "seed_unreachable":
        source_code = str(exc.details.get("source_code", "")).lower()
        reason = str(exc.details.get("reason", "")).lower()
        return source_code in {"fetch_failed"} or "urlopen error" in reason or "timed out" in reason
    return False


def run_generation(
    url: str,
    max_depth: int,
    max_pages: int,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> GenerationResult:
    """Run generation with user-friendly URL handling and scheme fallback."""
    attempts_info = build_url_attempts(url)
    attempts = attempts_info.attempt_urls
    display_input = attempts_info.display_input
    has_explicit_scheme = attempts_info.has_explicit_scheme
    last_error: CrawlError | None = None

    for attempt_index, attempt_url in enumerate(attempts):
        try:
            if progress_callback:
                progress_callback(
                    {
                        "stage": "resolving",
                        "message": f"Attempting {attempt_url}...",
                        "source_url": attempt_url,
                    }
                )
            run_result = run_generation_for_url(
                attempt_url,
                max_depth=max_depth,
                max_pages=max_pages,
                progress_callback=progress_callback,
            )
            return GenerationResult(
                llms_txt=run_result.llms_txt,
                discovered_count=run_result.discovered_count,
                processed_count=run_result.processed_count,
                source_url=attempt_url,
                failed_pages=run_result.failed_pages,
            )
        except CrawlError as exc:
            last_error = exc
            should_retry_with_http = (
                not has_explicit_scheme
                and attempt_index == 0
                and len(attempts) > 1
                and is_connection_failure(exc)
            )
            if should_retry_with_http:
                if progress_callback:
                    progress_callback(
                        {
                            "stage": "resolving",
                            "message": f"Failed to reach {attempt_url}. Retrying with {attempts[1]}...",
                        }
                    )
                continue
            raise

    raise CrawlError(
        f"Could not connect to {display_input} using HTTPS or HTTP.",
        code="connectivity_failed",
        details={"input": display_input, "attempts": attempts, "reason": str(last_error)},
    )
