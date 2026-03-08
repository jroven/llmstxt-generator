"""FastAPI application factory and route wiring."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates

from api.routes.generate import router as generate_router
from api.routes.pages import build_pages_router
from core.errors import AppError


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(title="llms.txt Generator")
    templates = Jinja2Templates(directory="templates")

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse | PlainTextResponse:
        """Map typed app errors to JSON for API routes and plain text elsewhere."""
        if request.url.path.startswith("/api/"):
            return JSONResponse(
                status_code=exc.http_status,
                content=exc.to_response(),
            )
        return PlainTextResponse(status_code=exc.http_status, content=exc.message)

    app.include_router(build_pages_router(templates))
    app.include_router(generate_router)
    return app


app = create_app()

