import threading
import time

import pytest

from autometa.config import Settings
from autometa.jobs.manager import JobConflict, JobManager
from autometa.persistence.database import Database
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
def job_setup(tmp_path):
    settings = Settings(
        _env_file=None,
        autometa_data_dir=tmp_path,
        autometa_job_workers=2,
    )
    database = Database(settings)
    database.create_schema()
    review = ReviewRepository(database).create("Job review", ReviewMode.GUIDED)
    manager = JobManager(JobRepository(database), max_workers=2)
    yield database, review, manager
    manager.shutdown()
    database.dispose()


def test_job_continues_without_sse_subscriber(job_setup) -> None:
    _, review, manager = job_setup

    def operation(context):
        context.emit("progress", {"completed": 1, "total": 1})
        return {"ok": True}

    job = manager.submit(review.id, "search", operation)
    wait_until(lambda: manager.get(job.id).state == "succeeded")

    events = manager.events(job.id, after_sequence=0)
    assert [event.event_type for event in events] == [
        "queued",
        "running",
        "progress",
        "succeeded",
    ]


def test_conflicting_stage_job_is_rejected(job_setup) -> None:
    _, review, manager = job_setup
    release = threading.Event()

    def blocking_operation(context):
        release.wait(timeout=1)
        return {"ok": True}

    manager.submit(review.id, "screening", blocking_operation)
    try:
        with pytest.raises(JobConflict):
            manager.submit(review.id, "screening", blocking_operation)
    finally:
        release.set()


def test_error_message_redacts_configured_secrets(job_setup) -> None:
    database, review, manager = job_setup
    secret = "JOB_SENTINEL_SECRET"
    database.settings.llm_api_key = secret

    def failing_operation(context):
        raise RuntimeError(f"provider failed with {secret}")

    job = manager.submit(review.id, "search", failing_operation)
    wait_until(lambda: manager.get(job.id).state == "failed")

    failed = manager.get(job.id)
    assert secret not in (failed.error or "")
    assert "[REDACTED]" in (failed.error or "")


def test_event_and_result_payloads_redact_configured_secrets(job_setup) -> None:
    database, review, manager = job_setup
    secret = "PAYLOAD_SENTINEL_SECRET"
    database.settings.llm_api_key = secret

    def operation(context):
        context.emit("progress", {"nested": {"message": secret}})
        return {"provider_response": [secret]}

    job = manager.submit(review.id, "search", operation)
    wait_until(lambda: manager.get(job.id).state == "succeeded")

    persisted = manager.get(job.id)
    events = manager.events(job.id)
    assert secret not in repr(persisted.result_reference)
    assert secret not in repr([event.payload for event in events])
    assert "[REDACTED]" in repr(persisted.result_reference)
    assert "[REDACTED]" in repr([event.payload for event in events])
