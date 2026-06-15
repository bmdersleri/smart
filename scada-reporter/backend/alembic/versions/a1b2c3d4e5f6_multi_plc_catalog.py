"""multi_plc_catalog

Revision ID: a1b2c3d4e5f6
Revises: decf6c1fe08b
Create Date: 2026-06-15 14:30:00.000000

Tag tablosuna çoklu-PLC + mutlak adres alanları ekler.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "decf6c1fe08b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tags", sa.Column("plc_name", sa.String(length=255), server_default="", nullable=False)
    )
    op.add_column("tags", sa.Column("plc_ip", sa.String(length=45), nullable=True))
    op.add_column("tags", sa.Column("plc_rack", sa.Integer(), server_default="0", nullable=False))
    op.add_column("tags", sa.Column("plc_slot", sa.Integer(), server_default="1", nullable=False))
    op.add_column("tags", sa.Column("s7_address", sa.String(length=128), nullable=True))
    op.add_column(
        "tags", sa.Column("data_type", sa.String(length=32), server_default="", nullable=False)
    )
    op.add_column(
        "tags", sa.Column("sample_interval", sa.Integer(), server_default="5", nullable=False)
    )
    op.add_column("tags", sa.Column("long_term", sa.Boolean(), server_default="0", nullable=False))
    op.add_column(
        "tags", sa.Column("daily_tracking", sa.Boolean(), server_default="0", nullable=False)
    )
    op.create_index("ix_tags_plc_ip", "tags", ["plc_ip"])


def downgrade() -> None:
    with op.batch_alter_table("tags") as b:
        b.drop_index("ix_tags_plc_ip")
        b.drop_column("daily_tracking")
        b.drop_column("long_term")
        b.drop_column("sample_interval")
        b.drop_column("data_type")
        b.drop_column("s7_address")
        b.drop_column("plc_slot")
        b.drop_column("plc_rack")
        b.drop_column("plc_ip")
        b.drop_column("plc_name")
