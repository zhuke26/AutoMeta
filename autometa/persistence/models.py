from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SqlEnum,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _id() -> str:
    return uuid4().hex


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _enum(enum_type: type[StrEnum]) -> SqlEnum:
    return SqlEnum(
        enum_type,
        values_callable=lambda values: [value.value for value in values],
        native_enum=False,
        validate_strings=True,
    )


class ReviewMode(StrEnum):
    GUIDED = "guided"
    SEARCH = "search"
    SCREENING = "screening"
    EXTRACTION = "extraction"
    META_ANALYSIS = "meta_analysis"


class ReviewStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETE = "complete"
    FAILED = "failed"
    DELETING = "deleting"


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    CANCELLED = "cancelled"


class ArtifactState(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    STALE = "stale"


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class Review(TimestampMixin, Base):
    __tablename__ = "reviews"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    entry_mode: Mapped[ReviewMode] = mapped_column(_enum(ReviewMode), nullable=False)
    status: Mapped[ReviewStatus] = mapped_column(
        _enum(ReviewStatus), default=ReviewStatus.DRAFT, nullable=False
    )
    current_stage: Mapped[str | None] = mapped_column(String(32))


class FileRecord(TimestampMixin, Base):
    __tablename__ = "files"
    __table_args__ = (UniqueConstraint("review_id", "sha256"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    review_id: Mapped[str] = mapped_column(
        ForeignKey("reviews.id", ondelete="CASCADE"), index=True, nullable=False
    )
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_name: Mapped[str] = mapped_column(String(255), nullable=False)
    relative_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), default="pdf", nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    parse_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)

class Job(TimestampMixin, Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    review_id: Mapped[str] = mapped_column(
        ForeignKey("reviews.id", ondelete="CASCADE"), index=True, nullable=False
    )
    stage: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    state: Mapped[JobState] = mapped_column(
        _enum(JobState), default=JobState.QUEUED, index=True, nullable=False
    )
    progress: Mapped[dict | None] = mapped_column(JSON)
    result_reference: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class JobEvent(Base):
    __tablename__ = "job_events"
    __table_args__ = (UniqueConstraint("job_id", "sequence"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class StageRun(TimestampMixin, Base):
    __tablename__ = "stage_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    review_id: Mapped[str] = mapped_column(
        ForeignKey("reviews.id", ondelete="CASCADE"), index=True, nullable=False
    )
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    job_id: Mapped[str | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    input_artifact_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    operation_kind: Mapped[str | None] = mapped_column(String(64))
    request_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    input_artifact_version_ids: Mapped[list] = mapped_column(
        JSON, default=list, nullable=False
    )
    output_artifact_version_ids: Mapped[list] = mapped_column(
        JSON, default=list, nullable=False
    )


class Artifact(TimestampMixin, Base):
    __tablename__ = "artifacts"
    __table_args__ = (UniqueConstraint("review_id", "kind"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    review_id: Mapped[str] = mapped_column(
        ForeignKey("reviews.id", ondelete="CASCADE"), index=True, nullable=False
    )
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[ArtifactState] = mapped_column(
        _enum(ArtifactState), default=ArtifactState.DRAFT, nullable=False
    )
    current_version_id: Mapped[str | None] = mapped_column(String(32))


class ArtifactVersion(Base):
    __tablename__ = "artifact_versions"
    __table_args__ = (UniqueConstraint("artifact_id", "version"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    artifact_id: Mapped[str] = mapped_column(
        ForeignKey("artifacts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSON)
    file_path: Mapped[str | None] = mapped_column(String(1024))
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    artifact_version_id: Mapped[str] = mapped_column(
        ForeignKey("artifact_versions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), default="approved", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LocalSetting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class ReviewEvent(Base):
    __tablename__ = "review_events"
    __table_args__ = (UniqueConstraint("review_id", "sequence"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    review_id: Mapped[str] = mapped_column(
        ForeignKey("reviews.id", ondelete="CASCADE"), index=True, nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[str | None] = mapped_column(String(32))
    event_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    producer: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    stage_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("stage_runs.id", ondelete="SET NULL"), index=True
    )
    job_id: Mapped[str | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), index=True
    )
    artifact_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("artifact_versions.id", ondelete="SET NULL"), index=True
    )
    elapsed_ms: Mapped[int | None] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class ResearcherEdit(Base):
    __tablename__ = "researcher_edits"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    review_id: Mapped[str] = mapped_column(
        ForeignKey("reviews.id", ondelete="CASCADE"), index=True, nullable=False
    )
    artifact_id: Mapped[str] = mapped_column(
        ForeignKey("artifacts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    from_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("artifact_versions.id", ondelete="CASCADE"), index=True
    )
    to_version_id: Mapped[str] = mapped_column(
        ForeignKey("artifact_versions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    changed_paths: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class ProvenanceEdge(Base):
    __tablename__ = "provenance_edges"
    __table_args__ = (
        UniqueConstraint("source_version_id", "target_version_id", "relation"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    review_id: Mapped[str] = mapped_column(
        ForeignKey("reviews.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source_version_id: Mapped[str] = mapped_column(
        ForeignKey("artifact_versions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    target_version_id: Mapped[str] = mapped_column(
        ForeignKey("artifact_versions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    relation: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class RerunRelationship(Base):
    __tablename__ = "rerun_relationships"
    __table_args__ = (UniqueConstraint("rerun_stage_run_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    review_id: Mapped[str] = mapped_column(
        ForeignKey("reviews.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source_stage_run_id: Mapped[str] = mapped_column(
        ForeignKey("stage_runs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    rerun_stage_run_id: Mapped[str] = mapped_column(
        ForeignKey("stage_runs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source_event_id: Mapped[str] = mapped_column(
        ForeignKey("review_events.id", ondelete="CASCADE"), index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
