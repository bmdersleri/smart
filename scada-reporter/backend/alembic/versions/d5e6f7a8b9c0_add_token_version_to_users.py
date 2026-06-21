"""add token_version to users

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-06-21 08:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5e6f7a8b9c0"
down_revision: str | Sequence[str] | None = "c4d5e6f7a8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add token_version column to users table (default 0)."""
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column(
                "token_version",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )


def downgrade() -> None:
    """Remove token_version column from users table."""
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("token_version")
