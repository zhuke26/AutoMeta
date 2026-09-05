from __future__ import annotations

import time

import pytest

from autometa.config import Settings
from autometa.jobs.manager import JobManager
from autometa.persistence.database import Database
from autometa.persistence.models import JobState, ReviewMode
from autometa.repositories.artifacts import ArtifactRepository
from autometa.repositories.jobs import JobRepository
from autometa.repositories.provenance import ProvenanceRepository
from autometa.repositories.reviews import ReviewRepository
from autometa.repositories.stage_runs import StageRunRepository
from autometa.schemas.artifacts import ArtifactWriteContext
from autometa.schemas.provenance import Producer
from autometa.services.artifacts import ArtifactService
from autometa.services.provenance import ProvenanceService
from autometa.services.reruns import RerunConflict, RerunService
from autometa.services.workflow_operations import (
    WorkflowExecution,
    WorkflowOperationRegistry,
)
from autometa.services.workflows import WorkflowCoordinator


def wait_for_terminal(manager: JobManager, job_id: str):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        job = manager.get(job_id)
        if job.state not in {"queued", "running"}:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job did not finish: {job_id}")


def make_rerun_service(tmp_path):
    database = Database(Settings(_env_file=None, autometa_data_dir=tmp_path))
    database.create_schema()
    review = ReviewRepository(database).create("Rerun", ReviewMode.GUIDED)
    provenance = ProvenanceService(ProvenanceRepository(database))
    artifacts = ArtifactService(ArtifactRepository(database), provenance)
    jobs = JobRepository(database)
    manager = JobManager(jobs, max_workers=1)
    stage_runs = StageRunRepository(database)
    coordinator = WorkflowCoordinator(manager, stage_runs, artifacts, provenance)
    registry = WorkflowOperationRegistry()
    service = RerunService(
        provenance=provenance,
        stage_runs=stage_runs,
        artifacts=artifacts,
        coordinator=coordinator,
        registry=registry,
    )
    return database, review, manager, artifacts, jobs, stage_runs, provenance, registry, service


def completed_source_run(database, review, artifacts, jobs, stage_runs, provenance):
    query = artifacts.save_draft(review.id, "query", {"raw_query": "A"})
    approved = artifacts.approve(review.id, query.artifact_id, query.version)
    source_job = jobs.create(review.id, "search")
    jobs.transition(source_job.id, JobState.RUNNING)
    jobs.transition(source_job.id, JobState.SUCCEEDED)
    source_run = stage_runs.create(
        review.id,
        "search",
        source_job.id,
        [approved.artifact_id],
        operation_kind="search.run",
        request_payload={"retmax": 10},
        input_artifact_version_ids=[approved.version_id],
    )
    source_run = stage_runs.transition(source_job.id, JobState.SUCCEEDED)
    source_output = artifacts.save_draft(
        review.id,
        "records",
        {"papers": [{"pmid": "1", "title": "First"}]},
        context=ArtifactWriteContext(
            producer=Producer.AGENT,
            stage_run_id=source_run.id,
            job_id=source_job.id,
            input_version_ids=(approved.version_id,),
            metadata={"operation_kind": "search.run"},
        ),
    )
    completed = provenance.record(
        review.id,
        "stage.completed",
        Producer.SYSTEM,
        stage="search",
        stage_run_id=source_run.id,
        job_id=source_job.id,
        artifact_version_id=source_output.version_id,
    )
    return approved, source_run, completed


def test_rerun_uses_exact_historical_inputs_and_records_lineage(tmp_path) -> None:
    setup = make_rerun_service(tmp_path)
    database, review, manager, artifacts, jobs, stage_runs, provenance, registry, service = setup
    approved, source_run, completed = completed_source_run(
        database, review, artifacts, jobs, stage_runs, provenance
    )

    def replay(execution: WorkflowExecution) -> dict:
        assert execution.request_payload == {"retmax": 10}
        assert [item.version_id for item in execution.input_versions] == [
            approved.version_id
        ]
        output = artifacts.save_draft(
            review.id,
            "records",
            {"papers": [{"pmid": "2", "title": "Rerun"}]},
            context=execution.context.artifact_context(),
        )
        return {"artifact_id": output.artifact_id, "version_id": output.version_id}

    registry.register("search.run", replay)
    job = service.rerun(review.id, completed.id)
    terminal = wait_for_terminal(manager, job.id)
    rerun = stage_runs.get_by_job(job.id)
    relationship = provenance.rerun_for_stage_run(rerun.id)

    assert terminal.state == "succeeded"
    assert rerun is not None
    assert rerun.id != source_run.id
    assert rerun.input_artifact_version_ids == [approved.version_id]
    assert len(rerun.output_artifact_version_ids) == 1
    assert relationship.source_event_id == completed.id
    assert relationship.source_stage_run_id == source_run.id
    assert relationship.rerun_stage_run_id == rerun.id
    assert [
        event.event_type
        for event in provenance.list_events(review.id)
        if event.stage_run_id == rerun.id
    ] == [
        "stage.queued",
        "rerun.started",
        "stage.running",
        "artifact.version_created",
        "stage.completed",
        "rerun.completed",
    ]

    manager.shutdown()
    database.dispose()


def test_rerun_rejects_unregistered_or_failed_source_events(tmp_path) -> None:
    setup = make_rerun_service(tmp_path)
    database, review, manager, artifacts, jobs, stage_runs, provenance, _, service = setup
    _, source_run, completed = completed_source_run(
        database, review, artifacts, jobs, stage_runs, provenance
    )

    with pytest.raises(RerunConflict, match="not registered"):
        service.rerun(review.id, completed.id)

    failed_event = provenance.record(
        review.id,
        "stage.failed",
        Producer.SYSTEM,
        stage="search",
        stage_run_id=source_run.id,
        job_id=source_run.job_id,
    )
    with pytest.raises(RerunConflict, match="completed"):
        service.rerun(review.id, failed_event.id)

    manager.shutdown()
    database.dispose()
