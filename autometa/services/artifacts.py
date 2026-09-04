from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import func, select, update

from autometa.persistence.models import (
    Approval,
    Artifact,
    ArtifactState,
    ArtifactVersion,
    Review,
)
from autometa.repositories.artifacts import ArtifactRepository
from autometa.schemas.artifacts import ArtifactView


ARTIFACT_ORDER = (
    "question_pico",
    "query",
    "records",
    "selected_studies",
    "sources",
    "plan",
    "code",
    "result",
)

ARTIFACT_STAGE = {
    "question_pico": "setup",
    "query": "search",
    "records": "search",
    "selected_studies": "screening",
    "sources": "extraction",
    "plan": "meta_analysis",
    "code": "meta_analysis",
    "result": "meta_analysis",
}


class ArtifactNotFound(LookupError):
    pass


class InvalidArtifactKind(ValueError):
    pass


class ArtifactConflict(RuntimeError):
    pass


class ArtifactService:
    def __init__(self, repository: ArtifactRepository):
        self.repository = repository

    def save_draft(self, review_id: str, kind: str, payload: dict) -> ArtifactView:
        self._validate_kind(kind)
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        content_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

        with self.repository.database.session() as session:
            if session.get(Review, review_id) is None:
                raise ArtifactNotFound(f"Review not found: {review_id}")
            artifact = self.repository.find(session, review_id, kind)
            if artifact is None:
                artifact = Artifact(
                    review_id=review_id,
                    stage=ARTIFACT_STAGE[kind],
                    kind=kind,
                )
                session.add(artifact)
                session.flush()

            latest = session.scalar(
                select(func.max(ArtifactVersion.version)).where(
                    ArtifactVersion.artifact_id == artifact.id
                )
            )
            version = ArtifactVersion(
                artifact_id=artifact.id,
                version=int(latest or 0) + 1,
                payload=payload,
                content_hash=content_hash,
            )
            session.add(version)
            session.flush()
            artifact.current_version_id = version.id
            artifact.state = ArtifactState.DRAFT
            self._revoke_approvals(session, artifact.id)
            self._mark_downstream_stale(session, review_id, kind)
            session.flush()
            return self._view(artifact, version, approved=False)

    def approve(self, review_id: str, artifact_id: str, version: int) -> ArtifactView:
        with self.repository.database.session() as session:
            artifact = session.get(Artifact, artifact_id)
            if artifact is None or artifact.review_id != review_id:
                raise ArtifactNotFound(artifact_id)
            if artifact.state is ArtifactState.STALE:
                raise ArtifactConflict(
                    "A stale artifact must be regenerated before approval"
                )
            current = self.repository.version(session, artifact.current_version_id)
            if current is None or current.version != version:
                raise ArtifactConflict("Only the current artifact version can be approved")
            approval = self.repository.approval(session, current.id)
            if approval is None:
                session.add(Approval(artifact_version_id=current.id))
            artifact.state = ArtifactState.APPROVED
            session.flush()
            return self._view(artifact, current, approved=True)

    def revoke(self, review_id: str, kind: str) -> ArtifactView:
        self._validate_kind(kind)
        with self.repository.database.session() as session:
            artifact = self.repository.find(session, review_id, kind)
            if artifact is None:
                raise ArtifactNotFound(kind)
            current = self.repository.version(session, artifact.current_version_id)
            if current is None:
                raise ArtifactNotFound(kind)
            approval = self.repository.approval(session, current.id)
            if approval is not None:
                approval.status = "revoked"
                approval.revoked_at = datetime.now(timezone.utc)
            artifact.state = ArtifactState.DRAFT
            self._mark_downstream_stale(session, review_id, kind)
            session.flush()
            return self._view(artifact, current, approved=False)

    def get_approved(self, review_id: str, kind: str) -> ArtifactView | None:
        self._validate_kind(kind)
        with self.repository.database.session() as session:
            artifact = self.repository.find(session, review_id, kind)
            if artifact is None or artifact.state != ArtifactState.APPROVED:
                return None
            current = self.repository.version(session, artifact.current_version_id)
            if current is None or self.repository.approval(session, current.id) is None:
                return None
            return self._view(artifact, current, approved=True)

    def get_current(self, review_id: str, kind: str) -> ArtifactView:
        self._validate_kind(kind)
        with self.repository.database.session() as session:
            artifact = self.repository.find(session, review_id, kind)
            if artifact is None:
                raise ArtifactNotFound(kind)
            current = self.repository.version(session, artifact.current_version_id)
            if current is None:
                raise ArtifactNotFound(kind)
            return self._view(
                artifact,
                current,
                approved=self.repository.approval(session, current.id) is not None,
            )

    def list(self, review_id: str) -> list[ArtifactView]:
        with self.repository.database.session() as session:
            if session.get(Review, review_id) is None:
                raise ArtifactNotFound(f"Review not found: {review_id}")
            artifacts = self.repository.list_for_review(session, review_id)
            by_kind = {artifact.kind: artifact for artifact in artifacts}
            result: list[ArtifactView] = []
            for kind in ARTIFACT_ORDER:
                artifact = by_kind.get(kind)
                if artifact is None:
                    continue
                current = self.repository.version(session, artifact.current_version_id)
                if current is None:
                    continue
                result.append(
                    self._view(
                        artifact,
                        current,
                        approved=self.repository.approval(session, current.id) is not None,
                    )
                )
            return result

    def get_state(self, review_id: str, kind: str) -> str | None:
        self._validate_kind(kind)
        with self.repository.database.session() as session:
            artifact = self.repository.find(session, review_id, kind)
            return artifact.state.value if artifact is not None else None

    @staticmethod
    def _view(
        artifact: Artifact,
        version: ArtifactVersion,
        approved: bool,
    ) -> ArtifactView:
        return ArtifactView(
            artifact_id=artifact.id,
            review_id=artifact.review_id,
            stage=artifact.stage,
            kind=artifact.kind,
            state=artifact.state,
            version=version.version,
            payload=version.payload or {},
            content_hash=version.content_hash,
            created_at=version.created_at,
            approved=approved,
        )

    @staticmethod
    def _validate_kind(kind: str) -> None:
        if kind not in ARTIFACT_ORDER:
            raise InvalidArtifactKind(f"Unsupported artifact kind: {kind}")

    def _revoke_approvals(self, session, artifact_id: str) -> None:
        version_ids = self.repository.versions_query(artifact_id)
        session.execute(
            update(Approval)
            .where(
                Approval.artifact_version_id.in_(version_ids),
                Approval.status == "approved",
            )
            .values(status="revoked", revoked_at=datetime.now(timezone.utc))
        )

    def _mark_downstream_stale(self, session, review_id: str, kind: str) -> None:
        downstream = ARTIFACT_ORDER[ARTIFACT_ORDER.index(kind) + 1 :]
        if downstream:
            session.execute(
                update(Artifact)
                .where(
                    Artifact.review_id == review_id,
                    Artifact.kind.in_(downstream),
                )
                .values(state=ArtifactState.STALE)
            )
