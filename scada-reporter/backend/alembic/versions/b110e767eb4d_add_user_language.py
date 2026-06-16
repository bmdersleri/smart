"""add user language

Revision ID: b110e767eb4d
Revises: f1a2b3c4d5e6
Create Date: 2026-06-16 21:35:58.861167

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b110e767eb4d"
down_revision: str | Sequence[str] | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add language preference column to users table."""
    op.add_column(
        "users",
        sa.Column("language", sa.String(length=5), nullable=False, server_default="en"),
    )


def downgrade() -> None:
    """Remove language column from users table."""
    op.drop_column("users", "language")
