from __future__ import annotations

from autometa.persistence.models import StageRun
from autometa.repositories.stage_runs import StageRunRepository
from autometa.schemas.jobs import JobView
from autometa.schemas.provenance import Producer
from autometa.services.artifacts import ArtifactNotFound, ArtifactService
from autometa.services.provenance import ProvenanceNotFound, ProvenanceService
from autometa.services.workflow_operations import (
    WorkflowExecution,
    WorkflowOperationRegistry,
)
from autometa.services.workflows import WorkflowCoordinator


class RerunNotFound(LookupError):
    pass


class RerunConflict(RuntimeError):
    pass


class RerunService:
    def __init__(
        self,
        *,
        provenance: ProvenanceService,
        stage_runs: StageRunRepository,
        artifacts: ArtifactService,
        coordinator: WorkflowCoordinator,
        registry: WorkflowOperationRegistry,
    ):
        self.provenance = provenance
        self.stage_runs = stage_runs
        self.artifacts = artifacts
        self.coordinator = coordinator
        self.registry = registry

    def rerun(self, review_id: str, source_event_id: str) -> JobView:
        try:
            event = self.provenance.get_event(review_id, source_event_id)
        except ProvenanceNotFound as exc:
            raise RerunNotFound(str(exc)) from exc
        if event.event_type != "stage.completed" or event.stage_run_id is None:
            raise RerunConflict("Only a completed stage event can be rerun")
        source_run = self.stage_runs.get(event.stage_run_id)
        if source_run is None or source_run.review_id != review_id:
            raise RerunNotFound(f"Stage run not found: {event.stage_run_id}")
        if source_run.status != "succeeded":
            raise RerunConflict("Only a completed stage run can be rerun")
        if not source_run.operation_kind or not self.registry.contains(
            source_run.operation_kind
        ):
            raise RerunConflict("The source workflow operation is not registered")
        try:
            input_versions = tuple(
                self.artifacts.get_version_by_id(review_id, version_id)
                for version_id in source_run.input_artifact_version_ids
            )
        except ArtifactNotFound as exc:
            raise RerunConflict("A historical workflow input is unavailable") from exc

        def operation(context):
            return self.registry.execute(
                source_run.operation_kind,
                WorkflowExecution(
                    review_id=review_id,
                    request_payload=dict(source_run.request_payload),
                    input_versions=input_versions,
                    context=context,
                ),
            )

        def link_rerun(rerun_stage_run: StageRun) -> None:
            self.provenance.add_rerun(
                review_id=review_id,
                source_stage_run_id=source_run.id,
                rerun_stage_run_id=rerun_stage_run.id,
                source_event_id=event.id,
            )
            self.provenance.record(
                review_id,
                "rerun.started",
                Producer.RESEARCHER,
                stage=source_run.stage,
                stage_run_id=rerun_stage_run.id,
                job_id=rerun_stage_run.job_id,
                payload={"source_event_id": event.id},
            )

        return self.coordinator.submit(
            review_id,
            source_run.stage,
            list(input_versions),
            operation,
            operation_kind=source_run.operation_kind,
            request_payload=dict(source_run.request_payload),
            rerun_source_event_id=event.id,
            on_stage_run_created=link_rerun,
        )
