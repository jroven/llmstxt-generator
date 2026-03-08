"""Generation API routes."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Form, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse

from api.schemas import GenerateRequest
from core.constants import DEFAULT_MAX_DEPTH, DEFAULT_MAX_PAGES, MAX_DEPTH_CAP, MAX_PAGES_CAP
from services.jobs import create_job, get_job, run_generation_job
from services.pipeline import run_generation


router = APIRouter()


@router.post("/generate", response_class=PlainTextResponse)
async def generate_from_url(
    url: str = Form(...),
    max_depth: int = Form(DEFAULT_MAX_DEPTH, ge=0, le=MAX_DEPTH_CAP),
    max_pages: int = Form(DEFAULT_MAX_PAGES, ge=1, le=MAX_PAGES_CAP),
) -> PlainTextResponse:
    """Accept a URL, orchestrate services, and return generated llms.txt text."""
    generation_result = run_generation(url=url, max_depth=max_depth, max_pages=max_pages)
    return PlainTextResponse(content=generation_result.llms_txt, media_type="text/plain")


@router.post("/api/generate", response_class=JSONResponse)
async def generate_from_url_json(payload: GenerateRequest) -> JSONResponse:
    """JSON API endpoint used by the frontend app."""
    generation_result = run_generation(
        url=payload.url,
        max_depth=payload.max_depth,
        max_pages=payload.max_pages,
    )
    return JSONResponse(
        content={
            "llms_txt": generation_result.llms_txt,
            "source_url": generation_result.source_url,
            "discovered_pages": generation_result.discovered_count,
            "processed_pages": generation_result.processed_count,
            "failed_pages": generation_result.failed_pages,
        }
    )


@router.post("/api/generate/start", response_class=JSONResponse)
async def start_generate_job(payload: GenerateRequest, background_tasks: BackgroundTasks) -> JSONResponse:
    """Create an async generation job and return a pollable job id."""
    job_id = create_job(initial_source_url=payload.url)
    background_tasks.add_task(run_generation_job, job_id, payload)
    return JSONResponse(content={"job_id": job_id, "status": "queued"})


@router.get("/api/jobs/{job_id}", response_class=JSONResponse)
async def get_generate_job(job_id: str) -> JSONResponse:
    """Return current job status for frontend polling."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JSONResponse(content=job)
