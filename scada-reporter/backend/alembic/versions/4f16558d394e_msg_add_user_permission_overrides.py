"""add user permission_overrides

Revision ID: 4f16558d394e
Revises: b110e767eb4d
Create Date: 2026-06-17 04:12:47.603632

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4f16558d394e"
down_revision: str | Sequence[str] | None = "b110e767eb4d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add permission_overrides column to users table."""
    op.add_column(
        "users",
        sa.Column(
            "permission_overrides",
            sa.JSON(),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    """Remove permission_overrides column from users table."""
    op.drop_column("users", "permission_overrides")
