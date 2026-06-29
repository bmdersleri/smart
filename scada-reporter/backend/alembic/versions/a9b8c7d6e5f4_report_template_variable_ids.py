"""report_templates.variable_ids

Revision ID: a9b8c7d6e5f4
Revises: f3a4b5c6d7e8
Create Date: 2026-06-29

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a9b8c7d6e5f4"
down_revision: str | None = "f3a4b5c6d7e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "report_templates",
        sa.Column("variable_ids", sa.Text(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("report_templates", "variable_ids")
