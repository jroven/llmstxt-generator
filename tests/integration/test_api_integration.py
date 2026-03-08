from __future__ import annotations

from fastapi.testclient import TestClient

from api.app import app
from services.pipeline import GenerationResult


client = TestClient(app)


def test_generate_json_endpoint(monkeypatch):
    def fake_run_generation(url: str, max_depth: int, max_pages: int, progress_callback=None):
        return GenerationResult(
            llms_txt="# Example\n",
            discovered_count=5,
            processed_count=4,
            source_url="https://example.com/",
            failed_pages=({"url": "https://example.com/bad", "code": "http_error", "reason": "bad"},),
        )

    monkeypatch.setattr("api.routes.generate.run_generation", fake_run_generation)

    response = client.post(
        "/api/generate",
        json={"url": "https://example.com", "max_depth": 1, "max_pages": 20},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["llms_txt"] == "# Example\n"
    assert body["discovered_pages"] == 5
    assert body["processed_pages"] == 4
    assert body["source_url"] == "https://example.com/"
    assert len(body["failed_pages"]) == 1


def test_async_job_endpoints(monkeypatch):
    store = {
        "job_id": "job-123",
        "status": "queued",
        "stage": "queued",
        "message": "Queued...",
        "source_url": "https://example.com",
        "discovered_pages": 0,
        "processed_pages": 0,
        "failed_count": 0,
        "failed_pages": [],
        "llms_txt": "",
    }

    def fake_create_job(initial_source_url: str) -> str:
        assert initial_source_url == "https://example.com"
        return "job-123"

    def fake_run_generation_job(job_id: str, payload) -> None:
        store.update(
            {
                "status": "done",
                "stage": "done",
                "message": "Generation complete.",
                "llms_txt": "# Example\n",
            }
        )

    def fake_get_job(job_id: str):
        if job_id != "job-123":
            return None
        return dict(store)

    monkeypatch.setattr("api.routes.generate.create_job", fake_create_job)
    monkeypatch.setattr("api.routes.generate.run_generation_job", fake_run_generation_job)
    monkeypatch.setattr("api.routes.generate.get_job", fake_get_job)

    start = client.post(
        "/api/generate/start",
        json={"url": "https://example.com", "max_depth": 1, "max_pages": 20},
    )
    assert start.status_code == 200
    assert start.json()["job_id"] == "job-123"

    poll = client.get("/api/jobs/job-123")
    assert poll.status_code == 200
    assert poll.json()["status"] == "done"
    assert poll.json()["llms_txt"] == "# Example\n"
