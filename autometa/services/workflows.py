from collections.abc import Callable
from urllib.parse import urlsplit

from autometa import __version__
from autometa.config import AgentStage
from autometa.jobs.manager import JobContext, JobManager
from autometa.persistence.models import StageRun
from autometa.repositories.stage_runs import StageRunRepository
from autometa.schemas.artifacts import ArtifactVersionView, ArtifactView
from autometa.schemas.jobs import JobView
from autometa.schemas.provenance import Producer
from autometa.services.artifacts import ArtifactService
from autometa.services.provenance import ProvenanceService


class WorkflowInputConflict(RuntimeError):
    pass


class WorkflowCoordinator:
    def __init__(
        self,
        manager: JobManager,
        stage_runs: StageRunRepository,
        artifacts: ArtifactService,
        provenance: ProvenanceService | None = None,
    ):
        self.manager = manager
        self.stage_runs = stage_runs
        self.artifacts = artifacts
        self.provenance = provenance or artifacts.provenance

    def require_approved(
        self,
        review_id: str,
        kinds: tuple[str, ...],
    ) -> list[ArtifactView]:
        approved: list[ArtifactView] = []
        for kind in kinds:
            artifact = self.artifacts.get_approved(review_id, kind)
            if artifact is None:
                display_name = kind.replace("_", " ").title()
                raise WorkflowInputConflict(
                    f"Approve {display_name} before starting this stage"
                )
            approved.append(artifact)
        return approved

    def submit(
        self,
        review_id: str,
        stage: str,
        input_artifacts: list[ArtifactView | ArtifactVersionView],
        operation: Callable[[JobContext], dict | None],
        *,
        operation_kind: str | None = None,
        request_payload: dict | None = None,
        rerun_source_event_id: str | None = None,
        on_stage_run_created: Callable[[StageRun], None] | None = None,
    ) -> JobView:
        input_ids = [artifact.artifact_id for artifact in input_artifacts]
        input_version_ids = tuple(
            artifact.version_id for artifact in input_artifacts
        )
        resolved_operation = operation_kind or f"{stage}.run"
        safe_request = self.provenance.safe_metadata(request_payload)
        metadata = self._execution_metadata(stage, resolved_operation)

        def on_created(job: JobView) -> str:
            stage_run = self.stage_runs.create(
                review_id,
                stage,
                job.id,
                input_ids,
                operation_kind=resolved_operation,
                request_payload=safe_request,
                input_artifact_version_ids=list(input_version_ids),
            )
            self.provenance.record(
                review_id,
                "stage.queued",
                Producer.SYSTEM,
                stage=stage,
                stage_run_id=stage_run.id,
                job_id=job.id,
                payload=metadata,
            )
            if on_stage_run_created is not None:
                on_stage_run_created(stage_run)
            return stage_run.id

        def on_state_change(job_id: str, state) -> None:
            stage_run = self.stage_runs.transition(job_id, state)
            event_type = {
                "running": "stage.running",
                "succeeded": "stage.completed",
                "failed": "stage.failed",
                "interrupted": "stage.interrupted",
                "cancelled": "stage.cancelled",
            }.get(state.value, f"stage.{state.value}")
            self.provenance.record(
                review_id,
                event_type,
                Producer.SYSTEM,
                stage=stage,
                stage_run_id=stage_run.id,
                job_id=job_id,
                payload=metadata,
            )
            if rerun_source_event_id is not None and state.value in {
                "succeeded",
                "failed",
                "cancelled",
                "interrupted",
            }:
                rerun_event = (
                    "rerun.completed" if state.value == "succeeded" else "rerun.failed"
                )
                self.provenance.record(
                    review_id,
                    rerun_event,
                    Producer.SYSTEM,
                    stage=stage,
                    stage_run_id=stage_run.id,
                    job_id=job_id,
                    payload={"source_event_id": rerun_source_event_id, **metadata},
                )

        return self.manager.submit(
            review_id,
            stage,
            operation,
            on_created=on_created,
            on_state_change=on_state_change,
            input_version_ids=input_version_ids,
            metadata=metadata,
        )

    def _execution_metadata(self, stage: str, operation_kind: str) -> dict:
        settings = self.manager.repository.database.settings
        endpoint = urlsplit(settings.llm_base_url)
        origin = f"{endpoint.scheme}://{endpoint.hostname or ''}"
        if endpoint.port is not None:
            origin = f"{origin}:{endpoint.port}"
        try:
            model = settings.model_for(AgentStage(stage))
        except ValueError:
            model = settings.llm_model
        return self.provenance.safe_metadata({
            "operation_kind": operation_kind,
            "model": model,
            "provider_origin": origin,
            "product_version": __version__,
        })
