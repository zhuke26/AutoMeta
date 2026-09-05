"""Create the initial AutoMeta persistence schema.

Revision ID: 0001
Revises:
Create Date: 2026-09-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "reviews",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("entry_mode", sa.String(length=13), nullable=False),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.Column("current_stage", sa.String(length=32)),
        *_timestamps(),
    )
    op.create_table(
        "files",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("review_id", sa.String(length=32), sa.ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("stored_name", sa.String(length=255), nullable=False),
        sa.Column("relative_path", sa.String(length=1024), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("parse_status", sa.String(length=32), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("review_id", "sha256"),
    )
    op.create_index("ix_files_review_id", "files", ["review_id"])
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("review_id", sa.String(length=32), sa.ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("state", sa.String(length=11), nullable=False),
        sa.Column("progress", sa.JSON()),
        sa.Column("result_reference", sa.JSON()),
        sa.Column("error", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        *_timestamps(),
    )
    op.create_index("ix_jobs_review_id", "jobs", ["review_id"])
    op.create_index("ix_jobs_stage", "jobs", ["stage"])
    op.create_index("ix_jobs_state", "jobs", ["state"])
    op.create_table(
        "job_events",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("job_id", sa.String(length=32), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("job_id", "sequence"),
    )
    op.create_index("ix_job_events_job_id", "job_events", ["job_id"])
    op.create_table(
        "stage_runs",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("review_id", sa.String(length=32), sa.ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("job_id", sa.String(length=32), sa.ForeignKey("jobs.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("input_artifact_ids", sa.JSON(), nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_stage_runs_review_id", "stage_runs", ["review_id"])
    op.create_index("ix_stage_runs_job_id", "stage_runs", ["job_id"])
    op.create_table(
        "artifacts",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("review_id", sa.String(length=32), sa.ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=8), nullable=False),
        sa.Column("current_version_id", sa.String(length=32)),
        *_timestamps(),
        sa.UniqueConstraint("review_id", "kind"),
    )
    op.create_index("ix_artifacts_review_id", "artifacts", ["review_id"])
    op.create_table(
        "artifact_versions",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("artifact_id", sa.String(length=32), sa.ForeignKey("artifacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON()),
        sa.Column("file_path", sa.String(length=1024)),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("artifact_id", "version"),
    )
    op.create_index("ix_artifact_versions_artifact_id", "artifact_versions", ["artifact_id"])
    op.create_table(
        "approvals",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("artifact_version_id", sa.String(length=32), sa.ForeignKey("artifact_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_approvals_artifact_version_id", "approvals", ["artifact_version_id"])
    op.create_table(
        "settings",
        sa.Column("key", sa.String(length=128), primary_key=True),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    for table in (
        "settings",
        "approvals",
        "artifact_versions",
        "artifacts",
        "stage_runs",
        "job_events",
        "jobs",
        "files",
        "reviews",
    ):
        op.drop_table(table)
