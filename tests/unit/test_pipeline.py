from __future__ import annotations

import pytest

from core.errors import CrawlError
from services import pipeline
from services.pipeline import GenerationForUrlResult


def test_run_generation_scheme_fallback_on_connection_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_run_generation_for_url(resolved_url: str, max_depth: int, max_pages: int, progress_callback=None):
        calls.append(resolved_url)
        if resolved_url.startswith("https://"):
            raise CrawlError("down", code="fetch_failed", details={"url": resolved_url})
        return GenerationForUrlResult(
            llms_txt="# ok\n",
            discovered_count=1,
            processed_count=1,
            failed_pages=tuple(),
        )

    monkeypatch.setattr(pipeline, "run_generation_for_url", fake_run_generation_for_url)

    result = pipeline.run_generation("example.com", max_depth=1, max_pages=5)

    assert calls == ["https://example.com", "http://example.com"]
    assert result.source_url == "http://example.com"


def test_run_generation_no_fallback_for_explicit_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run_generation_for_url(resolved_url: str, max_depth: int, max_pages: int, progress_callback=None):
        raise CrawlError("down", code="fetch_failed", details={"url": resolved_url})

    monkeypatch.setattr(pipeline, "run_generation_for_url", fake_run_generation_for_url)

    with pytest.raises(CrawlError):
        pipeline.run_generation("https://example.com", max_depth=1, max_pages=5)
