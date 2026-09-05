from __future__ import annotations

import time

from autometa.config import Settings
from autometa.jobs.manager import JobManager
from autometa.persistence.database import Database
from autometa.persistence.models import ReviewMode
from autometa.repositories.artifacts import ArtifactRepository
from autometa.repositories.jobs import JobRepository
from autometa.repositories.provenance import ProvenanceRepository
from autometa.repositories.reviews import ReviewRepository
from autometa.repositories.stage_runs import StageRunRepository
from autometa.schemas.jobs import StageRunView
from autometa.services.artifacts import ArtifactService
from autometa.services.provenance import ProvenanceService
from autometa.services.workflows import WorkflowCoordinator


def wait_for_terminal(manager: JobManager, job_id: str):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        job = manager.get(job_id)
        if job.state not in {"queued", "running"}:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job did not finish: {job_id}")


def make_workflow(tmp_path):
    settings = Settings(
        _env_file=None,
        autometa_data_dir=tmp_path,
        llm_base_url="https://user:password@example.test/v1?token=hidden",
        llm_api_key="secret-value",
        llm_model="default-model",
        search_model="search-model",
    )
    database = Database(settings)
    database.create_schema()
    review = ReviewRepository(database).create("Workflow", ReviewMode.GUIDED)
    provenance = ProvenanceService(ProvenanceRepository(database))
    artifacts = ArtifactService(ArtifactRepository(database), provenance)
    manager = JobManager(JobRepository(database), max_workers=1)
    stage_runs = StageRunRepository(database)
    coordinator = WorkflowCoordinator(manager, stage_runs, artifacts, provenance)
    return database, review, manager, artifacts, stage_runs, provenance, coordinator


def test_workflow_persists_exact_inputs_outputs_and_safe_metadata(tmp_path) -> None:
    database, review, manager, artifacts, stage_runs, provenance, coordinator = (
        make_workflow(tmp_path)
    )
    draft = artifacts.save_draft(review.id, "query", {"raw_query": "sleep"})
    approved = artifacts.approve(review.id, draft.artifact_id, draft.version)

    def operation(context):
        output = artifacts.save_draft(
            review.id,
            "records",
            {"papers": []},
            context=context.artifact_context(),
        )
        return {"artifact_id": output.artifact_id, "version_id": output.version_id}

    job = coordinator.submit(
        review.id,
        "search",
        [approved],
        operation,
        operation_kind="search.run",
        request_payload={"retmax": 100, "api_key": "must-not-persist"},
    )
    terminal = wait_for_terminal(manager, job.id)
    stage_run = stage_runs.get_by_job(job.id)

    assert terminal.state == "succeeded"
    assert stage_run is not None
    assert stage_run.operation_kind == "search.run"
    assert stage_run.request_payload == {"retmax": 100, "api_key": "[REDACTED]"}
    assert stage_run.input_artifact_version_ids == [approved.version_id]
    assert stage_run.output_artifact_version_ids == [terminal.result_reference["version_id"]]
    assert StageRunView.model_validate(stage_run).operation_kind == "search.run"
    events = [
        event
        for event in provenance.list_events(review.id)
        if event.stage_run_id == stage_run.id
    ]
    assert [event.event_type for event in events] == [
        "stage.queued",
        "stage.running",
        "artifact.version_created",
        "stage.completed",
    ]
    artifact_event = events[2]
    assert artifact_event.payload["operation_kind"] == "search.run"
    assert artifact_event.payload["model"] == "search-model"
    assert artifact_event.payload["provider_origin"] == "https://example.test"
    assert "password" not in repr(events)
    assert "hidden" not in repr(events)

    manager.shutdown()
    database.dispose()


def test_failed_workflow_records_a_terminal_event(tmp_path) -> None:
    database, review, manager, _, stage_runs, provenance, coordinator = (
        make_workflow(tmp_path)
    )

    def operation(_context):
        raise RuntimeError("provider failed")

    job = coordinator.submit(
        review.id,
        "screening",
        [],
        operation,
        operation_kind="screening.run",
        request_payload={"max_concurrency": 1},
    )
    terminal = wait_for_terminal(manager, job.id)
    stage_run = stage_runs.get_by_job(job.id)

    assert terminal.state == "failed"
    assert stage_run is not None
    assert stage_run.status == "failed"
    assert [
        event.event_type
        for event in provenance.list_events(review.id)
        if event.stage_run_id == stage_run.id
    ] == ["stage.queued", "stage.running", "stage.failed"]

    manager.shutdown()
    database.dispose()
