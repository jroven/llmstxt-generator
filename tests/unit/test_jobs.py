from __future__ import annotations

import time

import pytest

from core.errors import AppValidationError
from services import jobs
from services.pipeline import GenerationResult


@pytest.fixture(autouse=True)
def _reset_jobs() -> None:
    jobs.reset_jobs_for_tests()


def test_get_job_returns_defensive_copy() -> None:
    job_id = jobs.create_job("https://example.com")
    job_copy = jobs.get_job(job_id)
    assert job_copy is not None

    job_copy["status"] = "mutated"

    fresh = jobs.get_job(job_id)
    assert fresh is not None
    assert fresh["status"] == "queued"


def test_run_generation_job_success(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run_generation(url: str, max_depth: int, max_pages: int, progress_callback=None):
        if progress_callback:
            progress_callback({"stage": "crawling", "message": "Crawling..."})
        return GenerationResult(
            llms_txt="# Title\n",
            discovered_count=3,
            processed_count=2,
            source_url="https://example.com",
            failed_pages=tuple(),
        )

    monkeypatch.setattr(jobs, "run_generation", fake_run_generation)

    job_id = jobs.create_job("https://example.com")

    class Payload:
        url = "https://example.com"
        max_depth = 1
        max_pages = 10

    jobs.run_generation_job(job_id, Payload())
    final = jobs.get_job(job_id)
    assert final is not None
    assert final["status"] == "done"
    assert final["llms_txt"] == "# Title\n"


def test_run_generation_job_app_error_sets_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_run_generation(url: str, max_depth: int, max_pages: int, progress_callback=None):
        raise AppValidationError("bad url")

    monkeypatch.setattr(jobs, "run_generation", failing_run_generation)

    job_id = jobs.create_job("https://bad")

    class Payload:
        url = "https://bad"
        max_depth = 1
        max_pages = 10

    jobs.run_generation_job(job_id, Payload())
    final = jobs.get_job(job_id)
    assert final is not None
    assert final["status"] == "failed"
    assert final["message"] == "bad url"


def test_cleanup_expires_terminal_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jobs, "JOB_RETENTION_SECONDS", 1)

    base_time = time.time()
    monkeypatch.setattr(jobs.time, "time", lambda: base_time)

    old_job_id = jobs.create_job("https://example.com")
    jobs.set_job(old_job_id, status="done")

    # Advance time past retention and trigger cleanup path.
    monkeypatch.setattr(jobs.time, "time", lambda: base_time + 10)
    _ = jobs.create_job("https://example.com/new")

    assert jobs.get_job(old_job_id) is None


def test_cleanup_enforces_max_stored_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jobs, "MAX_STORED_JOBS", 2)

    first = jobs.create_job("https://example.com/1")
    second = jobs.create_job("https://example.com/2")
    third = jobs.create_job("https://example.com/3")

    assert jobs.get_job(third) is not None
    # One of the oldest jobs should be evicted once cap is exceeded.
    remaining = [jobs.get_job(first), jobs.get_job(second), jobs.get_job(third)]
    assert sum(1 for value in remaining if value is not None) == 2
