import time

import pytest
from fastapi.testclient import TestClient

from autometa.api.dependencies import get_database, get_job_manager
from autometa.api.main import app
from autometa.jobs.manager import JobManager
from autometa.persistence.models import ReviewMode
from autometa.repositories.jobs import JobRepository
from autometa.repositories.reviews import ReviewRepository


def wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition was not met before timeout")


@pytest.fixture
def job_client(database):
    manager = JobManager(JobRepository(database), max_workers=1)
    app.dependency_overrides[get_database] = lambda: database
    app.dependency_overrides[get_job_manager] = lambda: manager
    with TestClient(app) as test_client:
        yield test_client, database, manager
    app.dependency_overrides.clear()
    manager.shutdown()


def test_job_event_endpoint_replays_after_sequence(job_client) -> None:
    client, database, manager = job_client
    review = ReviewRepository(database).create("API job", ReviewMode.GUIDED)

    def operation(context):
        context.emit("progress", {"completed": 1})
        return {"artifact_id": "result-1"}

    job = manager.submit(review.id, "search", operation)
    wait_until(lambda: manager.get(job.id).state == "succeeded")

    response = client.get(f"/api/v1/jobs/{job.id}/events?after=2")
    assert response.status_code == 200
    assert "event: progress" in response.text
    assert "event: succeeded" in response.text
    assert "event: queued" not in response.text
    assert "event: running" not in response.text


def test_unknown_job_returns_not_found(job_client) -> None:
    client, _, _ = job_client
    assert client.get("/api/v1/jobs/not-found").status_code == 404
