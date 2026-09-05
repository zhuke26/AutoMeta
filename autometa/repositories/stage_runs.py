from sqlalchemy import select

from autometa.persistence.database import Database
from autometa.persistence.models import JobState, StageRun


class StageRunRepository:
    def __init__(self, database: Database):
        self.database = database

    def create(
        self,
        review_id: str,
        stage: str,
        job_id: str,
        input_artifact_ids: list[str],
        *,
        operation_kind: str | None = None,
        request_payload: dict | None = None,
        input_artifact_version_ids: list[str] | None = None,
    ) -> StageRun:
        with self.database.session() as session:
            stage_run = StageRun(
                review_id=review_id,
                stage=stage,
                job_id=job_id,
                status=JobState.QUEUED.value,
                input_artifact_ids=list(input_artifact_ids),
                operation_kind=operation_kind,
                request_payload=dict(request_payload or {}),
                input_artifact_version_ids=list(input_artifact_version_ids or []),
                output_artifact_version_ids=[],
            )
            session.add(stage_run)
            session.flush()
            return stage_run

    def add_output_version(self, stage_run_id: str, version_id: str) -> StageRun:
        with self.database.session() as session:
            stage_run = session.get(StageRun, stage_run_id)
            if stage_run is None:
                raise LookupError(stage_run_id)
            output_ids = list(stage_run.output_artifact_version_ids)
            if version_id not in output_ids:
                output_ids.append(version_id)
                stage_run.output_artifact_version_ids = output_ids
            session.flush()
            return stage_run

    def get_by_job(self, job_id: str) -> StageRun | None:
        with self.database.session() as session:
            return session.scalar(select(StageRun).where(StageRun.job_id == job_id))

    def transition(self, job_id: str, state: JobState | str) -> StageRun:
        with self.database.session() as session:
            stage_run = session.scalar(
                select(StageRun).where(StageRun.job_id == job_id)
            )
            if stage_run is None:
                raise LookupError(job_id)
            stage_run.status = state.value if isinstance(state, JobState) else state
            session.flush()
            return stage_run
