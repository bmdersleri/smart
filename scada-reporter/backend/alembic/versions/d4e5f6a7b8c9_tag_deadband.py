"""tag deadband (report-by-exception)

Revision ID: d4e5f6a7b8c9
Revises: c3f2a1b8d9e0
Create Date: 2026-06-16 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c3f2a1b8d9e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tags", sa.Column("deadband", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("tags", "deadband")
