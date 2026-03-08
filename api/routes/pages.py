"""Page/template and lightweight utility routes."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates

from core.constants import (
    DEFAULT_MAX_DEPTH,
    DEFAULT_MAX_PAGES,
    JOB_POLL_INTERVAL_MS,
    MAX_DEPTH_CAP,
    MAX_PAGES_CAP,
)


def build_pages_router(templates: Jinja2Templates) -> APIRouter:
    """Build routes that render templates and utility endpoints."""
    router = APIRouter()

    @router.get("/", response_class=HTMLResponse)
    async def render_index(request: Request) -> HTMLResponse:
        """Render the home page with URL input form."""
        app_config = {
            "default_max_depth": DEFAULT_MAX_DEPTH,
            "default_max_pages": DEFAULT_MAX_PAGES,
            "max_depth_cap": MAX_DEPTH_CAP,
            "max_pages_cap": MAX_PAGES_CAP,
            "job_poll_interval_ms": JOB_POLL_INTERVAL_MS,
        }
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"request": request, "app_config": app_config},
        )

    @router.get("/healthz", response_class=JSONResponse, include_in_schema=False)
    async def healthz() -> JSONResponse:
        """Lightweight health endpoint for uptime checks."""
        return JSONResponse(content={"status": "ok"})

    @router.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> Response:
        """Return an empty favicon response to avoid 404 noise in logs."""
        return Response(status_code=204)

    return router
