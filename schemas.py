"""Pydantic schemas for llms.txt generation workflow."""

from __future__ import annotations

from pydantic import BaseModel, Field, HttpUrl


class PageMetadata(BaseModel):
    """Metadata extracted from a single crawled page."""

    url: HttpUrl | str = Field(..., description="Canonical page URL.")
    title: str = Field(default="", description="Page title.")
    description: str = Field(default="", description="Meta description text.")


class SectionMetadata(BaseModel):
    """Logical section grouping for pages in llms.txt output."""

    heading: str = Field(..., description="Section heading text.")
    page_urls: list[HttpUrl | str] = Field(
        default_factory=list,
        description="URLs assigned to this section.",
    )


class SiteMetadata(BaseModel):
    """High-level metadata used to render llms.txt."""

    site_url: HttpUrl | str = Field(..., description="Root website URL.")
    site_title: str = Field(default="", description="Website title for H1.")
    summary: str = Field(default="", description="Website summary for blockquote.")
    sections: list[SectionMetadata] = Field(
        default_factory=list,
        description="Section definitions for llms.txt output.",
    )
