"""Helpers for user-facing URL input validation and normalization."""

from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import urlsplit

from core.errors import AppValidationError

_SCHEME_TYPO_MAP: dict[str, str] = {
    "htts": "https",
    "httpss": "https",
    "htp": "http",
}

_SCHEME_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9+\-.]*):(/*)(.*)$")


@dataclass(frozen=True)
class UrlAttempts:
    """Normalized URL attempts derived from a single user-provided URL input."""

    attempt_urls: tuple[str, ...]
    display_input: str
    has_explicit_scheme: bool


def build_url_attempts(raw_url: str) -> UrlAttempts:
    """
    Validate user URL input and return attempt URLs.

    Returns:
        UrlAttempts containing candidate attempt URLs and input metadata.
    """
    cleaned = (raw_url or "").strip()
    if not cleaned:
        raise AppValidationError(
            'Invalid URL: ""\nPlease provide a website URL, e.g.\nhttps://example.com'
        )

    match = _SCHEME_RE.match(cleaned)
    if match:
        scheme, slashes, remainder = match.group(1).lower(), match.group(2), match.group(3)

        # Detect common scheme typos and suggest a likely fix.
        if scheme in _SCHEME_TYPO_MAP:
            corrected_scheme = _SCHEME_TYPO_MAP[scheme]
            normalized_remainder = remainder.lstrip("/")
            suggestion = f"{corrected_scheme}://{normalized_remainder}"
            raise AppValidationError(
                f'Invalid URL: "{cleaned}"\nDid you mean: {suggestion} ?'
            )

        # Only http/https are supported.
        if scheme not in {"http", "https"}:
            raise AppValidationError(
                f'Invalid URL: "{cleaned}"\nOnly http:// and https:// URLs are supported.'
            )

        # Suggest correct slash format when someone provides http:/ or https:/.
        if slashes != "//":
            normalized_remainder = remainder.lstrip("/")
            suggestion = f"{scheme}://{normalized_remainder}"
            raise AppValidationError(
                f'Invalid URL: "{cleaned}"\nDid you mean: {suggestion} ?'
            )

        split = urlsplit(cleaned)
        if not split.netloc:
            raise AppValidationError(
                f'Invalid URL: "{cleaned}"\nPlease provide a website URL, e.g.\nhttps://example.com'
            )
        return UrlAttempts(
            attempt_urls=(cleaned,),
            display_input=cleaned,
            has_explicit_scheme=True,
        )

    # Handle missing colon typo forms like "https//example.com" or "http//example.com".
    lowered = cleaned.lower()
    if lowered.startswith("https//"):
        suggestion = "https://" + cleaned[len("https//") :].lstrip("/")
        raise AppValidationError(f'Invalid URL: "{cleaned}"\nDid you mean: {suggestion} ?')
    if lowered.startswith("http//"):
        suggestion = "http://" + cleaned[len("http//") :].lstrip("/")
        raise AppValidationError(f'Invalid URL: "{cleaned}"\nDid you mean: {suggestion} ?')

    normalized = cleaned.lstrip("/")
    if not normalized:
        raise AppValidationError(
            f'Invalid URL: "{cleaned}"\nPlease provide a website URL, e.g.\nhttps://example.com'
        )

    return UrlAttempts(
        attempt_urls=(f"https://{normalized}", f"http://{normalized}"),
        display_input=normalized,
        has_explicit_scheme=False,
    )
