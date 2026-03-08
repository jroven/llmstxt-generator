from __future__ import annotations

import pytest

from core.errors import AppValidationError, CrawlError
from services import crawler


SITE_HTML: dict[str, str] = {
    "https://example.com/": """
        <a href='/about'>About</a>
        <a href='/docs'>Docs</a>
        <a href='/stories?page=1'>Stories page 1</a>
        <a href='/stories?page=2'>Stories page 2</a>
        <a href='/auth/login/?next=/cms/pages/1/edit/'>Auth Login</a>
        <a href='/account/register/'>Account Register</a>
        <a href='/safe?redirect=/target'>Redirect Query</a>
        <a href='/about'>About Duplicate</a>
        <a href='mailto:test@example.com'>Ignore mailto</a>
        <a href='https://external.com/other'>External</a>
    """,
    "https://example.com/about": "<a href='/team'>Team</a>",
    "https://example.com/docs": "<a href='/team'>Team duplicate path</a>",
    "https://example.com/stories?page=1": "<p>Stories page one</p>",
    "https://example.com/team": "<p>Done</p>",
}


def _fake_fetch(url: str, fetch_cache=None) -> tuple[str, str]:
    if url not in SITE_HTML:
        raise CrawlError("not found", code="http_error", details={"url": url})
    return SITE_HTML[url], url


def test_crawl_site_bfs_same_domain_and_dedupe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(crawler, "_fetch_html", _fake_fetch)

    urls = crawler.crawl_site("https://example.com/", max_depth=2, max_pages=10)

    assert urls == [
        "https://example.com/",
        "https://example.com/about",
        "https://example.com/docs",
        "https://example.com/stories?page=1",
        "https://example.com/team",
    ]


def test_crawl_site_respects_max_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(crawler, "_fetch_html", _fake_fetch)

    urls = crawler.crawl_site("https://example.com/", max_depth=5, max_pages=2)

    assert urls == ["https://example.com/", "https://example.com/about"]


def test_crawl_site_invalid_url_raises() -> None:
    with pytest.raises(AppValidationError):
        crawler.crawl_site("not-a-url", max_depth=1, max_pages=5)


def test_crawl_site_seed_unreachable_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_fetch(url: str, fetch_cache=None) -> tuple[str, str]:
        raise CrawlError("boom", code="fetch_failed", details={"url": url})

    monkeypatch.setattr(crawler, "_fetch_html", fail_fetch)

    with pytest.raises(CrawlError) as exc_info:
        crawler.crawl_site("https://example.com/", max_depth=1, max_pages=5)

    assert exc_info.value.code == "seed_unreachable"


def test_crawl_site_collapses_pagination_query_variants(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(crawler, "_fetch_html", _fake_fetch)

    urls = crawler.crawl_site("https://example.com/", max_depth=2, max_pages=20)

    # Pagination variants of the same listing should collapse to one crawled URL.
    assert "https://example.com/stories?page=1" in urls
    assert "https://example.com/stories?page=2" not in urls


def test_crawl_site_filters_denylisted_auth_account_and_query_links(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(crawler, "_fetch_html", _fake_fetch)

    urls = crawler.crawl_site("https://example.com/", max_depth=2, max_pages=20)

    assert all("/auth/" not in url for url in urls)
    assert all("/account/" not in url for url in urls)
    assert all("redirect=" not in url for url in urls)
    assert all("next=" not in url for url in urls)
