from __future__ import annotations

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from autometa.persistence.database import Database
from autometa.persistence.models import Approval, Artifact, ArtifactVersion


class ArtifactRepository:
    def __init__(self, database: Database):
        self.database = database

    @staticmethod
    def find(session: Session, review_id: str, kind: str) -> Artifact | None:
        return session.scalar(
            select(Artifact).where(
                Artifact.review_id == review_id,
                Artifact.kind == kind,
            )
        )

    @staticmethod
    def list_for_review(session: Session, review_id: str) -> list[Artifact]:
        return list(session.scalars(select(Artifact).where(Artifact.review_id == review_id)))

    @staticmethod
    def version(session: Session, version_id: str | None) -> ArtifactVersion | None:
        return session.get(ArtifactVersion, version_id) if version_id else None

    @staticmethod
    def versions_query(artifact_id: str) -> Select:
        return select(ArtifactVersion.id).where(ArtifactVersion.artifact_id == artifact_id)

    @staticmethod
    def list_versions(session: Session, artifact_id: str) -> list[ArtifactVersion]:
        return list(
            session.scalars(
                select(ArtifactVersion)
                .where(ArtifactVersion.artifact_id == artifact_id)
                .order_by(ArtifactVersion.version.asc())
            )
        )

    @staticmethod
    def version_number(
        session: Session,
        artifact_id: str,
        version: int,
    ) -> ArtifactVersion | None:
        return session.scalar(
            select(ArtifactVersion).where(
                ArtifactVersion.artifact_id == artifact_id,
                ArtifactVersion.version == version,
            )
        )

    @staticmethod
    def approval(session: Session, version_id: str) -> Approval | None:
        return session.scalar(
            select(Approval).where(
                Approval.artifact_version_id == version_id,
                Approval.status == "approved",
            )
        )

    @staticmethod
    def latest_approval(session: Session, version_id: str) -> Approval | None:
        return session.scalar(
            select(Approval)
            .where(Approval.artifact_version_id == version_id)
            .order_by(Approval.created_at.desc(), Approval.id.desc())
        )
