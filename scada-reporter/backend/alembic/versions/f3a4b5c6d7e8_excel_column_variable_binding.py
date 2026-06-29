"""excel_template_columns variable-binding fields

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-06-29 13:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f3a4b5c6d7e8"
down_revision: str | None = "e2f3a4b5c6d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "excel_template_columns",
        sa.Column("source_type", sa.String(length=8), nullable=False, server_default="tag"),
    )
    op.add_column("excel_template_columns", sa.Column("variable_id", sa.Integer(), nullable=True))
    op.add_column(
        "excel_template_columns", sa.Column("write_mode", sa.String(length=8), nullable=True)
    )
    op.add_column(
        "excel_template_columns", sa.Column("reduce_op", sa.String(length=8), nullable=True)
    )
    op.add_column(
        "excel_template_columns",
        sa.Column("target_mode", sa.String(length=8), nullable=False, server_default="column"),
    )
    op.add_column(
        "excel_template_columns", sa.Column("target_cell", sa.String(length=8), nullable=True)
    )
    op.add_column(
        "excel_template_columns",
        sa.Column("variable_code_snapshot", sa.String(length=64), nullable=True),
    )
    if op.get_bind().dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_excel_col_variable_id",
            "excel_template_columns",
            "facility_variables",
            ["variable_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint("fk_excel_col_variable_id", "excel_template_columns", type_="foreignkey")
    for col in (
        "variable_code_snapshot",
        "target_cell",
        "target_mode",
        "reduce_op",
        "write_mode",
        "variable_id",
        "source_type",
    ):
        op.drop_column("excel_template_columns", col)
