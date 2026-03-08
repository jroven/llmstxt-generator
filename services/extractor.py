"""Content extraction service skeleton."""

from __future__ import annotations

from bs4 import BeautifulSoup

from core.errors import AppValidationError
from services.http_fetcher import shared_http_fetcher
from schemas import PageMetadata


def fetch_html(url: str) -> str:
    """
    Fetch raw HTML content for a given URL.

    Args:
        url: The page URL to fetch.

    Returns:
        The raw HTML string for the requested page.
    """
    # HTTP behavior is centralized in HttpFetcher for reuse across modules.
    return shared_http_fetcher.fetch_html(url)


def extract_page_metadata(url: str, html: str) -> PageMetadata:
    """
    Extract title and meta description from HTML and return structured metadata.

    Args:
        url: Source page URL.
        html: Raw HTML document content.

    Returns:
        Structured page metadata containing URL, title, and description.
    """
    if not html:
        raise AppValidationError(
            "HTML content is required for metadata extraction.",
            details={"field": "html", "url": url},
        )

    # Parse the document using the built-in HTML parser backend.
    soup = BeautifulSoup(html, "html.parser")

    # Extract title text robustly; get_text handles nested elements safely.
    if soup.title:
        title = soup.title.get_text(strip=True)
        # Normalize repeated whitespace/newlines into single spaces.
        if title:
            title = " ".join(title.split())
    else:
        title = ""

    # Extract the standard meta description content (case-insensitive name match).
    description_tag = soup.find(
        "meta",
        attrs={"name": lambda x: x and x.lower() == "description"},
    )
    if description_tag and description_tag.get("content"):
        description = description_tag.get("content", "").strip()
    else:
        description = ""

    return PageMetadata(url=url, title=title, description=description)
