import time

import pytest

from autometa.config import Settings
from autometa.jobs.manager import JobManager
from autometa.persistence.database import Database
from autometa.persistence.models import ReviewMode
from autometa.repositories.artifacts import ArtifactRepository
from autometa.repositories.jobs import JobRepository
from autometa.repositories.reviews import ReviewRepository
from autometa.repositories.stage_runs import StageRunRepository
from autometa.services.artifacts import ArtifactService
from autometa.services.workflows import WorkflowCoordinator, WorkflowInputConflict


@pytest.fixture
def workflow(tmp_path):
    database = Database(Settings(_env_file=None, autometa_data_dir=tmp_path))
    database.create_schema()
    review = ReviewRepository(database).create("Workflow", ReviewMode.GUIDED)
    manager = JobManager(JobRepository(database), max_workers=1)
    artifacts = ArtifactService(ArtifactRepository(database))
    stage_runs = StageRunRepository(database)
    coordinator = WorkflowCoordinator(manager, stage_runs, artifacts)
    yield review, manager, artifacts, stage_runs, coordinator
    manager.shutdown()
    database.dispose()


def _wait_for_terminal(manager: JobManager, job_id: str):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        job = manager.get(job_id)
        if job.state not in {"queued", "running"}:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job did not finish: {job_id}")


def test_require_approved_rejects_draft_and_returns_exact_inputs(workflow) -> None:
    review, _, artifacts, _, coordinator = workflow
    draft = artifacts.save_draft(review.id, "query", {"raw_query": "sleep[Title]"})

    with pytest.raises(WorkflowInputConflict, match="Approve Query"):
        coordinator.require_approved(review.id, ("query",))

    artifacts.approve(review.id, draft.artifact_id, draft.version)
    approved = coordinator.require_approved(review.id, ("query",))
    assert [item.artifact_id for item in approved] == [draft.artifact_id]


def test_submit_records_inputs_progress_result_and_success(workflow) -> None:
    review, manager, artifacts, stage_runs, coordinator = workflow
    draft = artifacts.save_draft(review.id, "query", {"raw_query": "sleep[Title]"})
    approved = artifacts.approve(review.id, draft.artifact_id, draft.version)

    def operation(context):
        context.emit("retrieving", {"completed": 2, "total": 4})
        return {"artifact_id": "records-1"}

    submitted = coordinator.submit(review.id, "search", [approved], operation)
    terminal = _wait_for_terminal(manager, submitted.id)
    stage_run = stage_runs.get_by_job(submitted.id)

    assert terminal.state == "succeeded"
    assert terminal.result_reference == {"artifact_id": "records-1"}
    assert terminal.progress == {"completed": 2, "total": 4}
    assert stage_run is not None
    assert stage_run.status == "succeeded"
    assert stage_run.input_artifact_ids == [approved.artifact_id]


def test_submit_mirrors_failure_without_masking_job_error(workflow) -> None:
    review, manager, _, stage_runs, coordinator = workflow

    def operation(_context):
        raise RuntimeError("workflow failed")

    submitted = coordinator.submit(review.id, "screening", [], operation)
    terminal = _wait_for_terminal(manager, submitted.id)
    stage_run = stage_runs.get_by_job(submitted.id)

    assert terminal.state == "failed"
    assert terminal.error == "workflow failed"
    assert stage_run is not None
    assert stage_run.status == "failed"
