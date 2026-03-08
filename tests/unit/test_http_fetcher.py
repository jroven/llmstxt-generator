from __future__ import annotations

from email.message import Message
from urllib.error import HTTPError, URLError

import pytest

from core.errors import AppValidationError, CrawlError
from services.fetch_cache import RunFetchCache
from services.http_fetcher import HttpFetcher


class FakeResponse:
    def __init__(
        self,
        body: bytes,
        *,
        content_type: str = "text/html; charset=utf-8",
        status: int = 200,
        url: str = "https://example.com/final",
    ) -> None:
        self._body = body
        self._url = url
        self.status = status
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    def read(self, n: int = -1) -> bytes:
        if n == -1:
            return self._body
        return self._body[:n]

    def geturl(self) -> str:
        return self._url

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_fetch_html_with_final_url_success_and_cache() -> None:
    calls = {"count": 0}

    def opener(request, timeout=0):
        calls["count"] += 1
        return FakeResponse(b"<html>ok</html>")

    fetcher = HttpFetcher(opener=opener, retries=0)
    cache = RunFetchCache()

    html_1, final_url_1 = fetcher.fetch_html_with_final_url("https://example.com", cache=cache)
    html_2, final_url_2 = fetcher.fetch_html_with_final_url("https://example.com", cache=cache)

    assert html_1 == "<html>ok</html>"
    assert final_url_1 == "https://example.com/final"
    assert (html_2, final_url_2) == (html_1, final_url_1)
    assert calls["count"] == 1


def test_fetch_html_rejects_non_html() -> None:
    fetcher = HttpFetcher(opener=lambda request, timeout=0: FakeResponse(b"{}", content_type="application/json"), retries=0)

    with pytest.raises(CrawlError) as exc_info:
        fetcher.fetch_html_with_final_url("https://example.com/data")

    assert exc_info.value.code == "non_html_content"


def test_fetch_html_rejects_oversized_body() -> None:
    fetcher = HttpFetcher(
        opener=lambda request, timeout=0: FakeResponse(b"x" * 12),
        retries=0,
        max_html_bytes=10,
    )

    with pytest.raises(CrawlError) as exc_info:
        fetcher.fetch_html_with_final_url("https://example.com")

    assert exc_info.value.code == "html_too_large"


def test_fetch_html_retries_http_error_and_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("services.http_fetcher.time.sleep", lambda _seconds: None)

    sequence = [
        HTTPError("https://example.com", 429, "Too Many Requests", hdrs=Message(), fp=None),
        FakeResponse(b"<html>ok</html>"),
    ]

    def opener(request, timeout=0):
        value = sequence.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    fetcher = HttpFetcher(opener=opener, retries=1)
    html, final = fetcher.fetch_html_with_final_url("https://example.com")

    assert html == "<html>ok</html>"
    assert final == "https://example.com/final"


def test_fetch_html_empty_url_raises_validation_error() -> None:
    fetcher = HttpFetcher(opener=lambda request, timeout=0: FakeResponse(b"<html></html>"), retries=0)

    with pytest.raises(AppValidationError):
        fetcher.fetch_html_with_final_url("")


def test_fetch_html_url_error_maps_to_fetch_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("services.http_fetcher.time.sleep", lambda _seconds: None)

    def opener(request, timeout=0):
        raise URLError("connection refused")

    fetcher = HttpFetcher(opener=opener, retries=1)

    with pytest.raises(CrawlError) as exc_info:
        fetcher.fetch_html_with_final_url("https://example.com")

    assert exc_info.value.code == "fetch_failed"
