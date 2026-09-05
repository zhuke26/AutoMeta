"""Add explicit file kinds for generated figures.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "files",
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="pdf"),
    )
    op.execute(
        "UPDATE files SET kind = 'csv' "
        "WHERE mime_type IN ('text/csv', 'application/csv', 'application/vnd.ms-excel')"
    )


def downgrade() -> None:
    with op.batch_alter_table("files") as batch_op:
        batch_op.drop_column("kind")
