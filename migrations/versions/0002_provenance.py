"""Add Review provenance, history, and rerun records.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("stage_runs", sa.Column("operation_kind", sa.String(length=64)))
    op.add_column(
        "stage_runs",
        sa.Column(
            "request_payload",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.add_column(
        "stage_runs",
        sa.Column(
            "input_artifact_version_ids",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.add_column(
        "stage_runs",
        sa.Column(
            "output_artifact_version_ids",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )

    op.create_table(
        "review_events",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column(
            "review_id",
            sa.String(length=32),
            sa.ForeignKey("reviews.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=32)),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("producer", sa.String(length=32), nullable=False),
        sa.Column(
            "stage_run_id",
            sa.String(length=32),
            sa.ForeignKey("stage_runs.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "job_id",
            sa.String(length=32),
            sa.ForeignKey("jobs.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "artifact_version_id",
            sa.String(length=32),
            sa.ForeignKey("artifact_versions.id", ondelete="SET NULL"),
        ),
        sa.Column("elapsed_ms", sa.Integer()),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("review_id", "sequence"),
    )
    for column in (
        "review_id",
        "event_type",
        "producer",
        "stage_run_id",
        "job_id",
        "artifact_version_id",
    ):
        op.create_index(f"ix_review_events_{column}", "review_events", [column])

    op.create_table(
        "researcher_edits",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column(
            "review_id",
            sa.String(length=32),
            sa.ForeignKey("reviews.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "artifact_id",
            sa.String(length=32),
            sa.ForeignKey("artifacts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "from_version_id",
            sa.String(length=32),
            sa.ForeignKey("artifact_versions.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "to_version_id",
            sa.String(length=32),
            sa.ForeignKey("artifact_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("changed_paths", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("review_id", "artifact_id", "from_version_id", "to_version_id"):
        op.create_index(f"ix_researcher_edits_{column}", "researcher_edits", [column])

    op.create_table(
        "provenance_edges",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column(
            "review_id",
            sa.String(length=32),
            sa.ForeignKey("reviews.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_version_id",
            sa.String(length=32),
            sa.ForeignKey("artifact_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_version_id",
            sa.String(length=32),
            sa.ForeignKey("artifact_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relation", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_version_id", "target_version_id", "relation"),
    )
    for column in ("review_id", "source_version_id", "target_version_id"):
        op.create_index(f"ix_provenance_edges_{column}", "provenance_edges", [column])

    op.create_table(
        "rerun_relationships",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column(
            "review_id",
            sa.String(length=32),
            sa.ForeignKey("reviews.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_stage_run_id",
            sa.String(length=32),
            sa.ForeignKey("stage_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "rerun_stage_run_id",
            sa.String(length=32),
            sa.ForeignKey("stage_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_event_id",
            sa.String(length=32),
            sa.ForeignKey("review_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("rerun_stage_run_id"),
    )
    for column in (
        "review_id",
        "source_stage_run_id",
        "rerun_stage_run_id",
        "source_event_id",
    ):
        op.create_index(
            f"ix_rerun_relationships_{column}",
            "rerun_relationships",
            [column],
        )


def downgrade() -> None:
    op.drop_table("rerun_relationships")
    op.drop_table("provenance_edges")
    op.drop_table("researcher_edits")
    op.drop_table("review_events")
    with op.batch_alter_table("stage_runs") as batch_op:
        batch_op.drop_column("output_artifact_version_ids")
        batch_op.drop_column("input_artifact_version_ids")
        batch_op.drop_column("request_payload")
        batch_op.drop_column("operation_kind")
