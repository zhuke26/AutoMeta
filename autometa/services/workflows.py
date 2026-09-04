from collections.abc import Callable

from autometa.jobs.manager import JobContext, JobManager
from autometa.repositories.stage_runs import StageRunRepository
from autometa.schemas.artifacts import ArtifactView
from autometa.schemas.jobs import JobView
from autometa.services.artifacts import ArtifactService


class WorkflowInputConflict(RuntimeError):
    pass


class WorkflowCoordinator:
    def __init__(
        self,
        manager: JobManager,
        stage_runs: StageRunRepository,
        artifacts: ArtifactService,
    ):
        self.manager = manager
        self.stage_runs = stage_runs
        self.artifacts = artifacts

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
        input_artifacts: list[ArtifactView],
        operation: Callable[[JobContext], dict | None],
    ) -> JobView:
        input_ids = [artifact.artifact_id for artifact in input_artifacts]
        return self.manager.submit(
            review_id,
            stage,
            operation,
            on_created=lambda job: self.stage_runs.create(
                review_id,
                stage,
                job.id,
                input_ids,
            ),
            on_state_change=lambda job_id, state: self.stage_runs.transition(
                job_id,
                state,
            ),
        )
