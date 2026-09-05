"""Scope file hash deduplication by Review and file kind.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NAMING_CONVENTION = {
    "uq": "uq_%(table_name)s_%(column_0_name)s",
}


def upgrade() -> None:
    with op.batch_alter_table(
        "files",
        recreate="always",
        naming_convention=_NAMING_CONVENTION,
    ) as batch_op:
        batch_op.drop_constraint("uq_files_review_id", type_="unique")
        batch_op.create_unique_constraint(
            "uq_files_review_kind_sha256",
            ["review_id", "kind", "sha256"],
        )


def downgrade() -> None:
    with op.batch_alter_table(
        "files",
        recreate="always",
        naming_convention=_NAMING_CONVENTION,
    ) as batch_op:
        batch_op.drop_constraint("uq_files_review_kind_sha256", type_="unique")
        batch_op.create_unique_constraint(
            "uq_files_review_id",
            ["review_id", "sha256"],
        )
