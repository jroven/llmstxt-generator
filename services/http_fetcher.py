"""Reusable HTTP fetcher shared across crawler and extractor services."""

from __future__ import annotations

import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from core.errors import AppValidationError, CrawlError
from services.fetch_cache import RunFetchCache


class HttpFetcher:
    """
    Small, reusable HTTP client for fetching HTML pages.

    This class centralizes timeout, retry, headers, response validation, and
    typed error conversion so service modules do not duplicate HTTP logic.
    """

    def __init__(
        self,
        *,
        timeout_seconds: float = 6.0,
        retries: int = 1,
        user_agent: str = "llms-txt-generator/0.1",
        max_html_bytes: int = 2_000_000,
        max_retry_after_seconds: float = 3.0,
        max_backoff_seconds: float = 2.0,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.retries = max(0, retries)
        self.user_agent = user_agent
        self.max_html_bytes = max_html_bytes
        self.max_retry_after_seconds = max_retry_after_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self.opener = opener

    def fetch_html(self, url: str) -> str:
        """Fetch HTML content and return only the decoded body."""
        html, _ = self.fetch_html_with_final_url(url)
        return html

    def _compute_retry_delay(self, attempt: int, http_error: HTTPError | None = None) -> float:
        """Compute retry delay with optional Retry-After support."""
        if http_error is not None:
            retry_after_value = http_error.headers.get("Retry-After")
            if retry_after_value:
                try:
                    parsed_retry_after = float(retry_after_value)
                    if parsed_retry_after > 0:
                        return min(parsed_retry_after, self.max_retry_after_seconds)
                except ValueError:
                    # Ignore invalid header values and use default backoff.
                    pass
        return min(0.5 * attempt, self.max_backoff_seconds)

    def fetch_html_with_final_url(
        self,
        url: str,
        cache: RunFetchCache | None = None,
    ) -> tuple[str, str]:
        """
        Fetch and return HTML plus final URL after redirects.

        Raises:
            AppValidationError: For malformed URL values.
            CrawlError: For network/HTTP failures or non-HTML responses.
        """
        if not url:
            raise AppValidationError(
                "URL is required.",
                details={"field": "url", "value": url},
            )

        if cache is not None:
            cached = cache.get(url)
            if cached is not None:
                return cached.html, cached.final_url

        last_error: Exception | None = None
        attempts = self.retries + 1
        request = Request(url, headers={"User-Agent": self.user_agent})

        for attempt in range(1, attempts + 1):
            try:
                with self.opener(request, timeout=self.timeout_seconds) as response:
                    final_url = response.geturl() or url
                    status = getattr(response, "status", None)
                    if status is not None and status >= 400:
                        raise CrawlError(
                            "HTTP request returned an error status.",
                            code="http_error",
                            details={"url": final_url, "status": status},
                        )

                    content_type = response.headers.get("Content-Type", "").lower()
                    if "text/html" not in content_type:
                        raise CrawlError(
                            "Fetched resource is not HTML content.",
                            code="non_html_content",
                            details={"url": final_url, "content_type": content_type},
                        )

                    # Read one extra byte so oversized responses can be detected.
                    body = response.read(self.max_html_bytes + 1)
                    if len(body) > self.max_html_bytes:
                        raise CrawlError(
                            "Fetched HTML exceeds maximum allowed size.",
                            code="html_too_large",
                            details={"url": final_url, "max_html_bytes": self.max_html_bytes},
                        )

                    charset = response.headers.get_content_charset() or "utf-8"
                    decoded_html = body.decode(charset, errors="replace")
                    result = (decoded_html, final_url)
                    if cache is not None:
                        cache.put(requested_url=url, final_url=final_url, html=decoded_html)
                    return result
            except CrawlError:
                # Content/type/size/status validation errors are deterministic.
                raise
            except ValueError as exc:
                # urllib can raise ValueError for malformed URLs.
                raise AppValidationError(
                    "Invalid URL format.",
                    details={"field": "url", "value": url, "reason": str(exc)},
                ) from exc
            except HTTPError as exc:
                last_error = exc
                if attempt < attempts:
                    time.sleep(self._compute_retry_delay(attempt=attempt, http_error=exc))
                    continue

                raise CrawlError(
                    "HTTP request returned an error status.",
                    code="http_error",
                    details={"url": url, "status": exc.code, "reason": str(exc)},
                ) from exc
            except (URLError, TimeoutError) as exc:
                last_error = exc
                if attempt < attempts:
                    time.sleep(self._compute_retry_delay(attempt=attempt))
                    continue

        raise CrawlError(
            "Failed to fetch HTML content from URL.",
            code="fetch_failed",
            details={"url": url, "reason": str(last_error), "attempts": attempts},
        ) from last_error


shared_http_fetcher = HttpFetcher()
