from __future__ import annotations

from collections import defaultdict

from services import pipeline
from services.http_fetcher import shared_http_fetcher


HTML_BY_URL = {
    "https://example.com/": "<a href='/docs'>Docs</a><a href='/broken'>Broken</a>",
    "https://example.com/docs": "<head><title>Docs</title><meta name='description' content='Documentation'></head>",
    "https://example.com/broken": "<head><title>Broken</title><meta name='description' content='Will fail later'></head>",
}


def test_run_generation_for_url_integration(monkeypatch):
    calls = defaultdict(int)

    def fake_fetch_html_with_final_url(url: str, cache=None):
        calls[url] += 1
        # Simulate extraction-time failure for one discovered page.
        if url == "https://example.com/broken" and calls[url] >= 2:
            from core.errors import CrawlError

            raise CrawlError("rate limited", code="http_error", details={"url": url})

        html = HTML_BY_URL.get(url)
        if html is None:
            from core.errors import CrawlError

            raise CrawlError("not found", code="http_error", details={"url": url})
        return html, url

    monkeypatch.setattr(shared_http_fetcher, "fetch_html_with_final_url", fake_fetch_html_with_final_url)

    result = pipeline.run_generation_for_url(
        resolved_url="https://example.com/",
        max_depth=1,
        max_pages=10,
    )

    assert result.discovered_count == 3
    assert result.processed_count == 2
    assert len(result.failed_pages) == 1
    assert result.failed_pages[0]["url"] == "https://example.com/broken"
    assert result.llms_txt.startswith("# ")
    assert "## Docs" in result.llms_txt
