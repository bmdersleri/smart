"""report_archive.variable_refs_json

Revision ID: d1e2f3a4b5c6
Revises: a9b8c7d6e5f4
Create Date: 2026-06-29

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d1e2f3a4b5c6"
down_revision: str | None = "a9b8c7d6e5f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "report_archive",
        sa.Column("variable_refs_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("report_archive", "variable_refs_json")
