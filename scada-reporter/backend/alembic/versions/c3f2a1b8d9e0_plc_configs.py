"""plc_configs

Revision ID: c3f2a1b8d9e0
Revises: 9b41a7b0986a
Create Date: 2026-06-15 20:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c3f2a1b8d9e0"
down_revision: str | None = "9b41a7b0986a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "plc_configs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("ip", sa.String(), nullable=False, server_default=""),
        sa.Column("rack", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("slot", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_plc_configs_name", "plc_configs", ["name"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_plc_configs_name", table_name="plc_configs")
    op.drop_table("plc_configs")
