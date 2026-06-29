"""facility variables + dependencies

Revision ID: e2f3a4b5c6d7
Revises: d0e1f2a3b4c5
Create Date: 2026-06-29 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e2f3a4b5c6d7"
down_revision: str | None = "d0e1f2a3b4c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "facility_variables",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("value_type", sa.String(length=16), nullable=False, server_default="number"),
        sa.Column("unit", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("expression_json", sa.Text(), nullable=False),
        sa.Column("null_policy", sa.String(length=12), nullable=False, server_default="skip"),
        sa.Column(
            "quality_policy", sa.String(length=12), nullable=False, server_default="good_only"
        ),  # noqa: E501
        sa.Column("default_time_grain", sa.String(length=8), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_table(
        "facility_variable_dependencies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("variable_id", sa.Integer(), nullable=False),
        sa.Column("depends_on_type", sa.String(length=8), nullable=False),
        sa.Column("depends_on_tag_id", sa.Integer(), nullable=True),
        sa.Column("depends_on_variable_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["variable_id"], ["facility_variables.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["depends_on_tag_id"], ["tags.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["depends_on_variable_id"], ["facility_variables.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fac_var_dep_variable_id", "facility_variable_dependencies", ["variable_id"])


def downgrade() -> None:
    op.drop_index("ix_fac_var_dep_variable_id", table_name="facility_variable_dependencies")
    op.drop_table("facility_variable_dependencies")
    op.drop_table("facility_variables")
