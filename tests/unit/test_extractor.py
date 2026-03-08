from __future__ import annotations

import pytest

from core.errors import AppValidationError
from services.extractor import extract_page_metadata


def test_extract_page_metadata_title_and_description_case_insensitive_meta() -> None:
    html = """
    <html>
      <head>
        <title>  Hello   World  </title>
        <meta name="Description" content="  Example description  ">
      </head>
      <body></body>
    </html>
    """

    metadata = extract_page_metadata("https://example.com", html)

    assert str(metadata.url) == "https://example.com/"
    assert metadata.title == "Hello World"
    assert metadata.description == "Example description"


def test_extract_page_metadata_missing_fields() -> None:
    html = "<html><head></head><body>No metadata</body></html>"

    metadata = extract_page_metadata("https://example.com/no-meta", html)

    assert metadata.title == ""
    assert metadata.description == ""


def test_extract_page_metadata_empty_html_raises_validation_error() -> None:
    with pytest.raises(AppValidationError):
        extract_page_metadata("https://example.com", "")
