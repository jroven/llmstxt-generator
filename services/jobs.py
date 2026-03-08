"""In-memory async job store and generation job runner."""

from __future__ import annotations

from threading import Lock
import time
from typing import Any, Protocol
from uuid import uuid4

from core.constants import JOB_RETENTION_SECONDS, MAX_STORED_JOBS
from core.errors import AppError
from services.pipeline import run_generation


class GenerationPayload(Protocol):
    """Typed protocol for generation payloads consumed by background jobs."""

    url: str
    max_depth: int
    max_pages: int


_JOB_LOCK = Lock()
_JOBS: dict[str, dict[str, Any]] = {}
_TERMINAL_JOB_STATUSES = {"done", "failed"}


def _cleanup_jobs_locked(now: float) -> None:
    """Remove stale jobs and bound total stored jobs.

    Notes:
        Must be called with `_JOB_LOCK` held.
    """
    stale_job_ids: list[str] = []
    for existing_job_id, job in _JOBS.items():
        status = str(job.get("status", ""))
        last_touch = float(job.get("updated_at") or job.get("created_at") or now)
        # Only expire completed/failed jobs; in-flight jobs remain until terminal.
        if status in _TERMINAL_JOB_STATUSES and (now - last_touch) > JOB_RETENTION_SECONDS:
            stale_job_ids.append(existing_job_id)

    for stale_job_id in stale_job_ids:
        _JOBS.pop(stale_job_id, None)

    # Hard cap as a safety net for high-throughput periods.
    excess = len(_JOBS) - MAX_STORED_JOBS
    if excess <= 0:
        return

    # Evict oldest jobs first by last update timestamp.
    oldest_first = sorted(
        _JOBS.items(),
        key=lambda item: float(item[1].get("updated_at") or item[1].get("created_at") or 0.0),
    )
    for evict_job_id, _ in oldest_first[:excess]:
        _JOBS.pop(evict_job_id, None)


def set_job(job_id: str, **updates: Any) -> None:
    """Thread-safe partial update for job state."""
    with _JOB_LOCK:
        _cleanup_jobs_locked(now=time.time())
        if job_id in _JOBS:
            _JOBS[job_id].update(updates)
            _JOBS[job_id]["updated_at"] = time.time()


def create_job(initial_source_url: str) -> str:
    """Create a queued in-memory generation job and return its id."""
    job_id = uuid4().hex
    with _JOB_LOCK:
        now = time.time()
        _cleanup_jobs_locked(now=now)
        _JOBS[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "stage": "queued",
            "message": "Queued...",
            "source_url": initial_source_url,
            "discovered_pages": 0,
            "processed_pages": 0,
            "failed_count": 0,
            "failed_pages": [],
            "llms_txt": "",
            "created_at": now,
            "updated_at": now,
        }
    return job_id


def get_job(job_id: str) -> dict[str, Any] | None:
    """Return job state by id, or None if missing/expired."""
    with _JOB_LOCK:
        _cleanup_jobs_locked(now=time.time())
        job = _JOBS.get(job_id)
        if job is None:
            return None
        # Return a defensive copy so callers cannot mutate shared in-memory state.
        return dict(job)


def run_generation_job(job_id: str, payload: GenerationPayload) -> None:
    """Background task: execute generation and write progress/results to job state."""
    set_job(job_id, status="running", stage="resolving", message="Starting...")
    try:
        generation_result = run_generation(
            url=payload.url,
            max_depth=payload.max_depth,
            max_pages=payload.max_pages,
            progress_callback=lambda data: set_job(job_id, **data),
        )
        set_job(
            job_id,
            status="done",
            stage="done",
            message="Generation complete.",
            llms_txt=generation_result.llms_txt,
            source_url=generation_result.source_url,
            discovered_pages=generation_result.discovered_count,
            processed_pages=generation_result.processed_count,
            failed_pages=generation_result.failed_pages,
            failed_count=len(generation_result.failed_pages),
        )
    except AppError as exc:
        set_job(
            job_id,
            status="failed",
            stage="failed",
            message=exc.message,
            error=exc.to_response(),
        )
    except Exception as exc:  # pragma: no cover - defensive fallback
        set_job(
            job_id,
            status="failed",
            stage="failed",
            message="Unexpected error during generation.",
            error={"error": "unexpected_error", "message": str(exc)},
        )


def reset_jobs_for_tests() -> None:
    """Clear in-memory jobs for deterministic tests."""
    with _JOB_LOCK:
        _JOBS.clear()
