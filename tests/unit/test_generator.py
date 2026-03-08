from __future__ import annotations

import pytest

from core.errors import AppValidationError
from schemas import PageMetadata, SiteMetadata
from services.generator import generate_llms_txt


def test_generate_llms_txt_basic_structure_and_sections() -> None:
    site = SiteMetadata(
        site_url="https://example.com",
        site_title="Example Site",
        summary="Example summary",
    )
    pages = [
        PageMetadata(url="https://example.com/docs/getting-started", title="Getting Started", description="Intro"),
        PageMetadata(url="https://example.com/blog/launch", title="Launch", description="Announcing launch"),
        PageMetadata(url="https://example.com/", title="Home", description="Homepage"),
    ]

    content = generate_llms_txt(pages, site)

    assert content.startswith("# Example Site\n\n> Example summary\n")
    assert "## Docs" in content
    assert "## Blog" in content
    assert "## Pages" in content
    assert "- [Getting Started](https://example.com/docs/getting-started): Intro" in content
    assert content.endswith("\n")


def test_generate_llms_txt_deduplicates_normalized_urls() -> None:
    site = SiteMetadata(site_url="https://example.com", site_title="", summary="")
    pages = [
        PageMetadata(url="https://example.com/docs", title="Docs A", description=""),
        PageMetadata(url="https://EXAMPLE.com/docs/", title="Docs B", description=""),
    ]

    content = generate_llms_txt(pages, site)

    # Only one docs page should appear after normalization-based dedupe.
    assert content.count("(https://example.com/docs)") + content.count("(https://EXAMPLE.com/docs/)") == 1


def test_generate_llms_txt_truncates_description_without_cutting_word() -> None:
    site = SiteMetadata(site_url="https://example.com", site_title="T", summary="S")
    long_description = "word " * 80
    pages = [PageMetadata(url="https://example.com/a", title="A", description=long_description)]

    content = generate_llms_txt(pages, site)

    assert "…" in content
    # Ensure no obvious broken word fragment at the end.
    line = next(line for line in content.splitlines() if line.startswith("- [A]"))
    assert not line.endswith(" …")


def test_generate_llms_txt_invalid_pages_payload() -> None:
    site = SiteMetadata(site_url="https://example.com", site_title="T", summary="S")

    with pytest.raises(AppValidationError):
        generate_llms_txt(pages=["bad"], site=site)  # type: ignore[arg-type]
