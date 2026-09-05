from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import func, select

from autometa.persistence.models import (
    Approval,
    Artifact,
    ArtifactState,
    ArtifactVersion,
    Review,
    StageRun,
)
from autometa.provenance import diff_payloads
from autometa.repositories.artifacts import ArtifactRepository
from autometa.repositories.provenance import ProvenanceRepository
from autometa.schemas.artifacts import (
    ArtifactDiffChange,
    ArtifactDiffView,
    ArtifactVersionView,
    ArtifactView,
    ArtifactWriteContext,
)
from autometa.schemas.provenance import Producer
from autometa.services.provenance import ProvenanceService

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
    def __init__(
        self,
        repository: ArtifactRepository,
        provenance: ProvenanceService | None = None,
    ):
        self.repository = repository
        self.provenance = provenance or ProvenanceService(
            ProvenanceRepository(repository.database)
        )

    def save_draft(
        self,
        review_id: str,
        kind: str,
        payload: dict,
        *,
        context: ArtifactWriteContext | None = None,
    ) -> ArtifactView:
        self._validate_kind(kind)
        write_context = context or ArtifactWriteContext()
        with self.provenance.sequence_lock, self.repository.database.session() as session:
            if session.get(Review, review_id) is None:
                raise ArtifactNotFound(f"Review not found: {review_id}")
            return self._save_draft(
                session,
                review_id,
                kind,
                payload,
                context=write_context,
            )

    def save_drafts(
        self,
        review_id: str,
        payloads: dict[str, dict],
        *,
        context: ArtifactWriteContext | None = None,
    ) -> dict[str, ArtifactView]:
        for kind in payloads:
            self._validate_kind(kind)
        write_context = context or ArtifactWriteContext()
        with self.provenance.sequence_lock, self.repository.database.session() as session:
            if session.get(Review, review_id) is None:
                raise ArtifactNotFound(f"Review not found: {review_id}")
            return {
                kind: self._save_draft(
                    session,
                    review_id,
                    kind,
                    payload,
                    context=write_context,
                )
                for kind, payload in payloads.items()
            }

    def approve(self, review_id: str, artifact_id: str, version: int) -> ArtifactView:
        with self.provenance.sequence_lock, self.repository.database.session() as session:
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
                self.provenance.record_in_session(
                    session,
                    review_id,
                    "artifact.approved",
                    Producer.RESEARCHER,
                    stage=artifact.stage,
                    artifact_version_id=current.id,
                    payload={"kind": artifact.kind, "version": current.version},
                )
            artifact.state = ArtifactState.APPROVED
            session.flush()
            return self._view(artifact, current, approved=True)

    def revoke(self, review_id: str, kind: str) -> ArtifactView:
        self._validate_kind(kind)
        with self.provenance.sequence_lock, self.repository.database.session() as session:
            artifact = self.repository.find(session, review_id, kind)
            if artifact is None:
                raise ArtifactNotFound(kind)
            current = self.repository.version(session, artifact.current_version_id)
            if current is None:
                raise ArtifactNotFound(kind)
            self._revoke_approvals(
                session,
                artifact,
                producer=Producer.RESEARCHER,
                reason="researcher_revoked",
            )
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

    def list_versions(self, review_id: str, kind: str) -> list[ArtifactVersionView]:
        self._validate_kind(kind)
        with self.repository.database.session() as session:
            artifact = self.repository.find(session, review_id, kind)
            if artifact is None:
                raise ArtifactNotFound(kind)
            return [
                self._version_view(session, artifact, version)
                for version in self.repository.list_versions(session, artifact.id)
            ]

    def get_version(
        self,
        review_id: str,
        kind: str,
        version: int,
    ) -> ArtifactVersionView:
        self._validate_kind(kind)
        with self.repository.database.session() as session:
            artifact = self.repository.find(session, review_id, kind)
            if artifact is None:
                raise ArtifactNotFound(kind)
            item = self.repository.version_number(session, artifact.id, version)
            if item is None:
                raise ArtifactNotFound(f"{kind} version {version}")
            return self._version_view(session, artifact, item)

    def get_version_by_id(
        self,
        review_id: str,
        version_id: str,
    ) -> ArtifactVersionView:
        with self.repository.database.session() as session:
            version = self.repository.version(session, version_id)
            if version is None:
                raise ArtifactNotFound(version_id)
            artifact = session.get(Artifact, version.artifact_id)
            if artifact is None or artifact.review_id != review_id:
                raise ArtifactNotFound(version_id)
            return self._version_view(session, artifact, version)

    def diff_versions(
        self,
        review_id: str,
        kind: str,
        from_version: int,
        to_version: int,
    ) -> ArtifactDiffView:
        self._validate_kind(kind)
        with self.repository.database.session() as session:
            artifact = self.repository.find(session, review_id, kind)
            if artifact is None:
                raise ArtifactNotFound(kind)
            before = self.repository.version_number(session, artifact.id, from_version)
            after = self.repository.version_number(session, artifact.id, to_version)
            if before is None or after is None:
                raise ArtifactNotFound("Artifact version not found")
            return ArtifactDiffView(
                artifact_id=artifact.id,
                kind=kind,
                from_version=from_version,
                to_version=to_version,
                changes=[
                    ArtifactDiffChange.model_validate(change)
                    for change in diff_payloads(before.payload or {}, after.payload or {})
                ],
            )

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
            version_id=version.id,
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

    def _version_view(
        self,
        session,
        artifact: Artifact,
        version: ArtifactVersion,
    ) -> ArtifactVersionView:
        approval = self.repository.latest_approval(session, version.id)
        return ArtifactVersionView(
            version_id=version.id,
            artifact_id=version.artifact_id,
            review_id=artifact.review_id,
            stage=artifact.stage,
            kind=artifact.kind,
            version=version.version,
            payload=version.payload or {},
            content_hash=version.content_hash,
            created_at=version.created_at,
            approval_status=approval.status if approval is not None else None,
            approved_at=approval.created_at if approval is not None else None,
            revoked_at=approval.revoked_at if approval is not None else None,
        )

    def _save_draft(
        self,
        session,
        review_id: str,
        kind: str,
        payload: dict,
        *,
        context: ArtifactWriteContext,
    ) -> ArtifactView:
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        content_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        artifact = self.repository.find(session, review_id, kind)
        previous: ArtifactVersion | None = None
        if artifact is None:
            artifact = Artifact(
                review_id=review_id,
                stage=ARTIFACT_STAGE[kind],
                kind=kind,
            )
            session.add(artifact)
            session.flush()
        else:
            previous = self.repository.version(session, artifact.current_version_id)

        latest = session.scalar(
            select(func.max(ArtifactVersion.version)).where(
                ArtifactVersion.artifact_id == artifact.id
            )
        )
        self._revoke_approvals(
            session,
            artifact,
            producer=context.producer,
            reason="new_version",
        )
        self._mark_downstream_stale(session, review_id, kind)
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

        changes = diff_payloads(previous.payload or {}, payload) if previous else []
        if previous is not None and context.producer is Producer.RESEARCHER and changes:
            self.provenance.add_edit_in_session(
                session,
                review_id=review_id,
                artifact_id=artifact.id,
                from_version_id=previous.id,
                to_version_id=version.id,
                changed_paths=[change["path"] for change in changes],
            )
        for source_version_id in context.input_version_ids:
            self.provenance.add_edge_in_session(
                session,
                review_id=review_id,
                source_version_id=source_version_id,
                target_version_id=version.id,
            )
        if context.stage_run_id is not None:
            stage_run = session.get(StageRun, context.stage_run_id)
            if stage_run is None or stage_run.review_id != review_id:
                raise ArtifactConflict("Stage run does not belong to this Review")
            output_ids = list(stage_run.output_artifact_version_ids)
            if version.id not in output_ids:
                output_ids.append(version.id)
                stage_run.output_artifact_version_ids = output_ids
        self.provenance.record_in_session(
            session,
            review_id,
            "artifact.version_created",
            context.producer,
            stage=artifact.stage,
            stage_run_id=context.stage_run_id,
            job_id=context.job_id,
            artifact_version_id=version.id,
            payload={
                "kind": kind,
                "version": version.version,
                "content_hash": content_hash,
                "changed_paths": [change["path"] for change in changes],
                **context.metadata,
            },
        )
        session.flush()
        return self._view(artifact, version, approved=False)

    @staticmethod
    def _validate_kind(kind: str) -> None:
        if kind not in ARTIFACT_ORDER:
            raise InvalidArtifactKind(f"Unsupported artifact kind: {kind}")

    def _revoke_approvals(
        self,
        session,
        artifact: Artifact,
        *,
        producer: Producer,
        reason: str,
    ) -> None:
        approvals = list(
            session.scalars(
                select(Approval)
                .join(ArtifactVersion, Approval.artifact_version_id == ArtifactVersion.id)
                .where(
                    ArtifactVersion.artifact_id == artifact.id,
                    Approval.status == "approved",
                )
            )
        )
        for approval in approvals:
            approval.status = "revoked"
            approval.revoked_at = datetime.now(timezone.utc)
            self.provenance.record_in_session(
                session,
                artifact.review_id,
                "artifact.revoked",
                producer,
                stage=artifact.stage,
                artifact_version_id=approval.artifact_version_id,
                payload={"kind": artifact.kind, "reason": reason},
            )

    def _mark_downstream_stale(self, session, review_id: str, kind: str) -> None:
        downstream = ARTIFACT_ORDER[ARTIFACT_ORDER.index(kind) + 1 :]
        if not downstream:
            return
        artifacts = list(
            session.scalars(
                select(Artifact).where(
                    Artifact.review_id == review_id,
                    Artifact.kind.in_(downstream),
                )
            )
        )
        stale_version_ids: set[str] = set()
        for artifact in artifacts:
            current = self.repository.version(session, artifact.current_version_id)
            if current is None:
                continue
            stale_version_ids.add(current.id)
            self._revoke_approvals(
                session,
                artifact,
                producer=Producer.SYSTEM,
                reason="upstream_changed",
            )
            if artifact.state is ArtifactState.STALE:
                continue
            artifact.state = ArtifactState.STALE
            self.provenance.record_in_session(
                session,
                review_id,
                "artifact.stale",
                Producer.SYSTEM,
                stage=artifact.stage,
                artifact_version_id=current.id,
                payload={"kind": artifact.kind, "upstream_kind": kind},
            )
        if stale_version_ids:
            for stage_run in session.scalars(
                select(StageRun).where(
                    StageRun.review_id == review_id,
                    StageRun.status == "succeeded",
                )
            ):
                if stale_version_ids.intersection(stage_run.output_artifact_version_ids):
                    stage_run.status = "stale"
                    self.provenance.record_in_session(
                        session,
                        review_id,
                        "stage.stale",
                        Producer.SYSTEM,
                        stage=stage_run.stage,
                        stage_run_id=stage_run.id,
                        job_id=stage_run.job_id,
                        payload={"upstream_kind": kind},
                    )
