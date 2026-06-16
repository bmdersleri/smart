"""excel templates + columns

Revision ID: f1a2b3c4d5e6
Revises: e5f6a7b8c9d0
Create Date: 2026-06-16 17:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "excel_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("file_blob", sa.LargeBinary(), nullable=False),
        sa.Column("sheet_name", sa.String(length=255), nullable=False),
        sa.Column("header_row", sa.Integer(), nullable=False),
        sa.Column("date_col", sa.String(length=4), nullable=False),
        sa.Column("data_start_row", sa.Integer(), nullable=False),
        sa.Column("date_mode", sa.String(length=8), nullable=False, server_default="write"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "excel_template_columns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("col_letter", sa.String(length=4), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=True),
        sa.Column("agg", sa.String(length=8), nullable=False, server_default="avg"),
        sa.Column("source_code", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(["template_id"], ["excel_templates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_excel_template_columns_template_id", "excel_template_columns", ["template_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_excel_template_columns_template_id", table_name="excel_template_columns")
    op.drop_table("excel_template_columns")
    op.drop_table("excel_templates")
