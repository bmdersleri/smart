"""index tag_readings.timestamp (dashboard scan -> index)

Revision ID: a7c2e9f04b18
Revises: 4f16558d394e
Create Date: 2026-06-20 12:20:00.000000

The composite PK is (tag_id, timestamp), so timestamp-only filters
(max(timestamp), count over 24h/1h windows on the dashboard overview)
fell back to a full table scan — ~2.5s each on a multi-million-row table.
A standalone index on timestamp makes those queries milliseconds.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a7c2e9f04b18"
down_revision: str | None = "4f16558d394e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_tag_readings_timestamp", "tag_readings", ["timestamp"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_tag_readings_timestamp", table_name="tag_readings")
