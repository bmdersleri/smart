"""add compliance report packs

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-06-28 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d0e1f2a3b4c5"
down_revision: str | None = "c9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "compliance_report_packs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("permit_id", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.DateTime(), nullable=False),
        sa.Column("period_end", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("events_snapshot_json", sa.Text(), nullable=True),
        sa.Column("archive_id", sa.Integer(), nullable=True),
        sa.Column("pdf_blob", sa.LargeBinary(), nullable=True),
        sa.Column("xlsx_blob", sa.LargeBinary(), nullable=True),
        sa.Column("json_blob", sa.LargeBinary(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("prepared_by", sa.Integer(), nullable=True),
        sa.Column("approved_by", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["permit_id"], ["compliance_permits.id"]),
        sa.ForeignKeyConstraint(["archive_id"], ["report_archive.id"]),
        sa.ForeignKeyConstraint(["prepared_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_compliance_report_packs_permit_period",
        "compliance_report_packs",
        ["permit_id", "period_start"],
    )
    op.create_index(
        "ix_compliance_report_packs_status",
        "compliance_report_packs",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_compliance_report_packs_status",
        table_name="compliance_report_packs",
    )
    op.drop_index(
        "ix_compliance_report_packs_permit_period",
        table_name="compliance_report_packs",
    )
    op.drop_table("compliance_report_packs")
