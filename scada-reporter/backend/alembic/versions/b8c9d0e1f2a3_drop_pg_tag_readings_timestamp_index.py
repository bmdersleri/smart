"""drop redundant standalone timestamp index on tag_readings (PostgreSQL only)

On TimescaleDB the hypertable partitions tag_readings by ``timestamp`` (chunk
exclusion) and the composite ``(tag_id, timestamp)`` covers tag+time range
scans, so the standalone ``ix_tag_readings_timestamp`` btree is redundant and
only slows down the high-rate poller writes. Dropped on PostgreSQL only; kept on
SQLite (no hypertable) where it still backs the dashboard timestamp-only scans.

Revision ID: b8c9d0e1f2a3
Revises: c3d4e5f6a7b8
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b8c9d0e1f2a3"
down_revision: str | Sequence[str] | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.drop_index("ix_tag_readings_timestamp", table_name="tag_readings")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.create_index("ix_tag_readings_timestamp", "tag_readings", ["timestamp"], unique=False)
