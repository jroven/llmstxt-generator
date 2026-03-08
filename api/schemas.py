"""API-layer request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field

from core.constants import DEFAULT_MAX_DEPTH, DEFAULT_MAX_PAGES, MAX_DEPTH_CAP, MAX_PAGES_CAP


class GenerateRequest(BaseModel):
    """Incoming payload for llms.txt generation requests."""

    url: str = Field(..., description="Site URL to crawl.")
    max_depth: int = Field(
        default=DEFAULT_MAX_DEPTH,
        ge=0,
        le=MAX_DEPTH_CAP,
        description="Crawl depth limit.",
    )
    max_pages: int = Field(
        default=DEFAULT_MAX_PAGES,
        ge=1,
        le=MAX_PAGES_CAP,
        description="Maximum pages to process.",
    )

