"""add users role check constraint

Revision ID: b2c3d4e5f6a7
Revises: 13eeb0cb4f16
Create Date: 2026-06-21 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "13eeb0cb4f16"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add CHECK constraint ensuring users.role is one of admin/operator/viewer."""
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.create_check_constraint(
            "ck_users_role_valid",
            "role IN ('admin','operator','viewer')",
        )


def downgrade() -> None:
    """Drop the users.role CHECK constraint."""
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_constraint("ck_users_role_valid", type_="check")
