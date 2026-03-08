from __future__ import annotations

import pytest

from core.errors import AppValidationError
from core.url_input import UrlAttempts, build_url_attempts


def test_build_url_attempts_explicit_https() -> None:
    result = build_url_attempts("https://example.com/docs")
    assert result == UrlAttempts(
        attempt_urls=("https://example.com/docs",),
        display_input="https://example.com/docs",
        has_explicit_scheme=True,
    )


def test_build_url_attempts_missing_scheme_tries_https_then_http() -> None:
    result = build_url_attempts("example.com/path")
    assert result.attempt_urls == ("https://example.com/path", "http://example.com/path")
    assert result.display_input == "example.com/path"
    assert result.has_explicit_scheme is False


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("htts://example.com", "Did you mean: https://example.com ?"),
        ("htp://example.com", "Did you mean: http://example.com ?"),
        ("https:/example.com", "Did you mean: https://example.com ?"),
        ("https//example.com", "Did you mean: https://example.com ?"),
        ("ftp://example.com", "Only http:// and https:// URLs are supported."),
    ],
)
def test_build_url_attempts_validation_errors(raw: str, expected: str) -> None:
    with pytest.raises(AppValidationError) as exc_info:
        build_url_attempts(raw)

    assert expected in exc_info.value.message
