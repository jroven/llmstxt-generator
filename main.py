"""FastAPI entrypoint for generating llms.txt from a target website."""

from __future__ import annotations

from threading import Lock
from typing import Any, Callable
from uuid import uuid4
from urllib.parse import urlsplit

from fastapi import BackgroundTasks, FastAPI, Form, HTTPException, Request
from pydantic import BaseModel, Field
from fastapi.responses import JSONResponse
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.templating import Jinja2Templates

from core.errors import AppError, CrawlError
from core.url_input import build_url_attempts
from schemas import PageMetadata, SiteMetadata
from services.crawler import crawl_site
from services.extractor import extract_page_metadata
from services.fetch_cache import RunFetchCache
from services.generator import generate_llms_txt
from services.http_fetcher import shared_http_fetcher

app = FastAPI(title="llms.txt Generator")
templates = Jinja2Templates(directory="templates")
_JOB_LOCK = Lock()
_JOBS: dict[str, dict[str, Any]] = {}


class GenerateRequest(BaseModel):
    """Incoming payload for llms.txt generation requests."""

    url: str = Field(..., description="Site URL to crawl.")
    max_depth: int = Field(default=1, ge=0, description="Crawl depth limit.")
    max_pages: int = Field(default=20, ge=1, le=200, description="Maximum pages to process.")


def _run_generation_for_url(
    resolved_url: str,
    max_depth: int,
    max_pages: int,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[str, int, int, list[dict[str, str]]]:
    """Run crawl -> extract -> generate pipeline for a fully-resolved URL."""
    fetch_cache = RunFetchCache()

    if progress_callback:
        progress_callback({"stage": "crawling", "message": "Crawling site links..."})

    discovered_urls: list[str] = crawl_site(
        resolved_url,
        max_depth=max_depth,
        max_pages=max_pages,
        fetch_cache=fetch_cache,
        progress_callback=progress_callback,
    )

    if progress_callback:
        progress_callback(
            {
                "stage": "extracting",
                "message": "Extracting page metadata...",
                "discovered_pages": len(discovered_urls),
                "processed_pages": 0,
                "failed_count": 0,
            }
        )

    pages: list[PageMetadata] = []
    failed_pages: list[dict[str, str]] = []
    for index, page_url in enumerate(discovered_urls, start=1):
        try:
            html, _ = shared_http_fetcher.fetch_html_with_final_url(
                page_url, cache=fetch_cache
            )
            page_metadata = extract_page_metadata(page_url, html)
            pages.append(page_metadata)
        except AppError as exc:
            # Skip individual page failures so one bad page does not abort the run.
            failed_pages.append(
                {
                    "url": page_url,
                    "code": exc.code,
                    "reason": exc.message,
                }
            )
            continue
        finally:
            if progress_callback:
                progress_callback(
                    {
                        "stage": "extracting",
                        "message": f"Extracting metadata ({index}/{len(discovered_urls)})...",
                        "discovered_pages": len(discovered_urls),
                        "processed_pages": len(pages),
                        "failed_count": len(failed_pages),
                    }
                )

    if not pages:
        raise CrawlError(
            "Could not extract metadata from any crawled pages.",
            code="metadata_extraction_failed",
            details={"url": resolved_url},
        )

    # Prefer root page metadata for site-level fields; fallback to URL domain.
    input_domain = urlsplit(resolved_url).netloc or "Site"
    root_page = next(
        (p for p in pages if str(p.url).rstrip("/") == resolved_url.rstrip("/")),
        pages[0],
    )
    inferred_site_title = (root_page.title or "").strip() or input_domain
    inferred_summary = (root_page.description or "").strip() or "Site summary goes here."

    site_metadata = SiteMetadata(
        site_url=resolved_url,
        site_title=inferred_site_title,
        summary=inferred_summary,
        sections=[],
    )
    if progress_callback:
        progress_callback({"stage": "generating", "message": "Building llms.txt document..."})
    llms_txt_output = generate_llms_txt(pages, site_metadata)
    return llms_txt_output, len(discovered_urls), len(pages), failed_pages


def _is_connection_failure(exc: CrawlError) -> bool:
    """Return True when an error indicates network/connectivity failure."""
    if exc.code == "fetch_failed":
        return True
    if exc.code == "seed_unreachable":
        source_code = str(exc.details.get("source_code", "")).lower()
        reason = str(exc.details.get("reason", "")).lower()
        return source_code in {"fetch_failed"} or "urlopen error" in reason or "timed out" in reason
    return False


def _run_generation(
    url: str,
    max_depth: int,
    max_pages: int,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[str, int, int, str, list[dict[str, str]]]:
    """Run generation with user-friendly URL handling and scheme fallback."""
    attempts, display_input, has_explicit_scheme = build_url_attempts(url)
    last_error: CrawlError | None = None

    for attempt_index, attempt_url in enumerate(attempts):
        try:
            if progress_callback:
                progress_callback(
                    {
                        "stage": "resolving",
                        "message": f"Attempting {attempt_url}...",
                        "source_url": attempt_url,
                    }
                )
            llms_txt_output, discovered_count, processed_count, failed_pages = (
                _run_generation_for_url(
                    attempt_url,
                    max_depth=max_depth,
                    max_pages=max_pages,
                    progress_callback=progress_callback,
                )
            )
            return llms_txt_output, discovered_count, processed_count, attempt_url, failed_pages
        except CrawlError as exc:
            last_error = exc
            should_retry_with_http = (
                not has_explicit_scheme
                and attempt_index == 0
                and len(attempts) > 1
                and _is_connection_failure(exc)
            )
            if should_retry_with_http:
                if progress_callback:
                    progress_callback(
                        {
                            "stage": "resolving",
                            "message": f"Failed to reach {attempt_url}. Retrying with {attempts[1]}...",
                        }
                    )
                continue
            raise

    raise CrawlError(
        f"Could not connect to {display_input} using HTTPS or HTTP.",
        code="connectivity_failed",
        details={"input": display_input, "attempts": attempts, "reason": str(last_error)},
    )


def _set_job(job_id: str, **updates: Any) -> None:
    """Thread-safe partial update for job state."""
    with _JOB_LOCK:
        if job_id in _JOBS:
            _JOBS[job_id].update(updates)


def _run_generation_job(job_id: str, payload: GenerateRequest) -> None:
    """Background task: execute generation and write progress/results to job state."""
    _set_job(job_id, status="running", stage="resolving", message="Starting...")
    try:
        llms_txt_output, discovered_count, processed_count, resolved_url, failed_pages = (
            _run_generation(
                url=payload.url,
                max_depth=payload.max_depth,
                max_pages=payload.max_pages,
                progress_callback=lambda data: _set_job(job_id, **data),
            )
        )
        _set_job(
            job_id,
            status="done",
            stage="done",
            message="Generation complete.",
            llms_txt=llms_txt_output,
            source_url=resolved_url,
            discovered_pages=discovered_count,
            processed_pages=processed_count,
            failed_pages=failed_pages,
            failed_count=len(failed_pages),
        )
    except AppError as exc:
        _set_job(
            job_id,
            status="failed",
            stage="failed",
            message=exc.message,
            error=exc.to_response(),
        )
    except Exception as exc:  # pragma: no cover - defensive fallback
        _set_job(
            job_id,
            status="failed",
            stage="failed",
            message="Unexpected error during generation.",
            error={"error": "unexpected_error", "message": str(exc)},
        )


@app.exception_handler(AppError)
async def handle_app_error(request: Request, exc: AppError) -> JSONResponse | PlainTextResponse:
    """Map typed app errors to JSON for API routes and plain text elsewhere."""
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            status_code=exc.http_status,
            content=exc.to_response(),
        )
    return PlainTextResponse(status_code=exc.http_status, content=exc.message)


@app.get("/", response_class=HTMLResponse)
async def render_index(request: Request) -> HTMLResponse:
    """Render the home page with URL input form."""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"request": request},
    )


@app.get("/healthz", response_class=JSONResponse, include_in_schema=False)
async def healthz() -> JSONResponse:
    """Lightweight health endpoint for uptime checks."""
    return JSONResponse(content={"status": "ok"})


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    """Return an empty favicon response to avoid 404 noise in logs."""
    return Response(status_code=204)


@app.post("/generate", response_class=PlainTextResponse)
async def generate_from_url(
    url: str = Form(...),
    max_depth: int = Form(1),
    max_pages: int = Form(20, le=200),
) -> PlainTextResponse:
    """Accept a URL, orchestrate services, and return generated llms.txt text."""
    llms_txt_output, _, _, _, _ = _run_generation(
        url=url, max_depth=max_depth, max_pages=max_pages
    )
    return PlainTextResponse(content=llms_txt_output, media_type="text/plain")


@app.post("/api/generate", response_class=JSONResponse)
async def generate_from_url_json(payload: GenerateRequest) -> JSONResponse:
    """JSON API endpoint used by the frontend app."""
    llms_txt_output, discovered_count, processed_count, resolved_url, failed_pages = _run_generation(
        url=payload.url,
        max_depth=payload.max_depth,
        max_pages=payload.max_pages,
    )
    return JSONResponse(
        content={
            "llms_txt": llms_txt_output,
            "source_url": resolved_url,
            "discovered_pages": discovered_count,
            "processed_pages": processed_count,
            "failed_pages": failed_pages,
        }
    )


@app.post("/api/generate/start", response_class=JSONResponse)
async def start_generate_job(payload: GenerateRequest, background_tasks: BackgroundTasks) -> JSONResponse:
    """Create an async generation job and return a pollable job id."""
    job_id = uuid4().hex
    with _JOB_LOCK:
        _JOBS[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "stage": "queued",
            "message": "Queued...",
            "source_url": payload.url,
            "discovered_pages": 0,
            "processed_pages": 0,
            "failed_count": 0,
            "failed_pages": [],
            "llms_txt": "",
        }
    background_tasks.add_task(_run_generation_job, job_id, payload)
    return JSONResponse(content={"job_id": job_id, "status": "queued"})


@app.get("/api/jobs/{job_id}", response_class=JSONResponse)
async def get_generate_job(job_id: str) -> JSONResponse:
    """Return current job status for frontend polling."""
    with _JOB_LOCK:
        job = _JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JSONResponse(content=job)
