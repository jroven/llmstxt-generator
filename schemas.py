"""Pydantic schemas for llms.txt generation workflow."""

from __future__ import annotations

from pydantic import BaseModel, Field, HttpUrl


class PageMetadata(BaseModel):
    """Metadata extracted from a single crawled page."""

    url: HttpUrl = Field(..., description="Canonical page URL.")
    title: str = Field(default="", description="Page title.")
    description: str = Field(default="", description="Meta description text.")


class SiteMetadata(BaseModel):
    """High-level metadata used to render llms.txt."""

    site_url: HttpUrl = Field(..., description="Root website URL.")
    site_title: str = Field(default="", description="Website title for H1.")
    summary: str = Field(default="", description="Website summary for blockquote.")
