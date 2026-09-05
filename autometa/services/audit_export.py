from __future__ import annotations

from datetime import datetime, timezone

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select

from autometa import __version__
from autometa.persistence.database import Database
from autometa.persistence.models import (
    Approval,
    Artifact,
    ArtifactVersion,
    FileRecord,
    Job,
    JobEvent,
    Review,
    StageRun,
)
from autometa.services.provenance import ProvenanceNotFound, ProvenanceService


class AuditExportService:
    def __init__(self, database: Database, provenance: ProvenanceService):
        self.database = database
        self.provenance = provenance

    def build(self, review_id: str) -> dict:
        with self.database.session() as session:
            review = session.get(Review, review_id)
            if review is None:
                raise ProvenanceNotFound(f"Review not found: {review_id}")
            files = list(
                session.scalars(
                    select(FileRecord)
                    .where(FileRecord.review_id == review_id)
                    .order_by(FileRecord.created_at.asc(), FileRecord.id.asc())
                )
            )
            artifacts = list(
                session.scalars(
                    select(Artifact)
                    .where(Artifact.review_id == review_id)
                    .order_by(Artifact.created_at.asc(), Artifact.id.asc())
                )
            )
            artifact_rows = []
            for artifact in artifacts:
                versions = list(
                    session.scalars(
                        select(ArtifactVersion)
                        .where(ArtifactVersion.artifact_id == artifact.id)
                        .order_by(ArtifactVersion.version.asc())
                    )
                )
                version_rows = []
                for version in versions:
                    approvals = list(
                        session.scalars(
                            select(Approval)
                            .where(Approval.artifact_version_id == version.id)
                            .order_by(Approval.created_at.asc(), Approval.id.asc())
                        )
                    )
                    version_rows.append(
                        {
                            "id": version.id,
                            "version": version.version,
                            "payload": version.payload or {},
                            "content_hash": version.content_hash,
                            "created_at": version.created_at,
                            "approvals": [
                                {
                                    "status": approval.status,
                                    "created_at": approval.created_at,
                                    "revoked_at": approval.revoked_at,
                                }
                                for approval in approvals
                            ],
                        }
                    )
                artifact_rows.append(
                    {
                        "id": artifact.id,
                        "stage": artifact.stage,
                        "kind": artifact.kind,
                        "state": artifact.state.value,
                        "current_version_id": artifact.current_version_id,
                        "versions": version_rows,
                    }
                )
            jobs = list(
                session.scalars(
                    select(Job)
                    .where(Job.review_id == review_id)
                    .order_by(Job.created_at.asc(), Job.id.asc())
                )
            )
            job_rows = []
            for job in jobs:
                events = list(
                    session.scalars(
                        select(JobEvent)
                        .where(JobEvent.job_id == job.id)
                        .order_by(JobEvent.sequence.asc())
                    )
                )
                job_rows.append(
                    {
                        "id": job.id,
                        "stage": job.stage,
                        "state": job.state.value,
                        "progress": job.progress,
                        "result_reference": job.result_reference,
                        "error": job.error,
                        "created_at": job.created_at,
                        "updated_at": job.updated_at,
                        "started_at": job.started_at,
                        "finished_at": job.finished_at,
                        "events": [
                            {
                                "sequence": event.sequence,
                                "event_type": event.event_type,
                                "payload": event.payload,
                                "created_at": event.created_at,
                            }
                            for event in events
                        ],
                    }
                )
            stage_runs = list(
                session.scalars(
                    select(StageRun)
                    .where(StageRun.review_id == review_id)
                    .order_by(StageRun.created_at.asc(), StageRun.id.asc())
                )
            )

        graph = self.provenance.graph(review_id)
        export = {
            "schema_version": 1,
            "product_version": __version__,
            "exported_at": datetime.now(timezone.utc),
            "review": {
                "id": review.id,
                "name": review.name,
                "entry_mode": review.entry_mode.value,
                "status": review.status.value,
                "current_stage": review.current_stage,
                "created_at": review.created_at,
                "updated_at": review.updated_at,
            },
            "files": [
                {
                    "id": item.id,
                    "original_name": item.original_name,
                    "kind": item.kind,
                    "mime_type": item.mime_type,
                    "size_bytes": item.size_bytes,
                    "sha256": item.sha256,
                    "parse_status": item.parse_status,
                    "created_at": item.created_at,
                }
                for item in files
            ],
            "artifacts": artifact_rows,
            "jobs": job_rows,
            "stage_runs": [
                {
                    "id": item.id,
                    "stage": item.stage,
                    "job_id": item.job_id,
                    "status": item.status,
                    "operation_kind": item.operation_kind,
                    "request_payload": item.request_payload,
                    "input_artifact_version_ids": item.input_artifact_version_ids,
                    "output_artifact_version_ids": item.output_artifact_version_ids,
                    "created_at": item.created_at,
                    "updated_at": item.updated_at,
                }
                for item in stage_runs
            ],
            "events": graph.events,
            "edges": graph.edges,
            "researcher_edits": graph.edits,
            "rerun_relationships": graph.reruns,
        }
        return self.provenance.redactor.payload(jsonable_encoder(export))
