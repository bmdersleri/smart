"""msg=add grafana_panels to report_templates

Revision ID: 46644a7e7f25
Revises: e1f2a3b4c5d6
Create Date: 2026-06-23 07:39:57.754008

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "46644a7e7f25"
down_revision: str | Sequence[str] | None = "e1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "report_templates",
        sa.Column("grafana_panels", sa.Text(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("report_templates", "grafana_panels")
