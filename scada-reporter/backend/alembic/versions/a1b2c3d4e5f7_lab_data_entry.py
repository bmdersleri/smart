"""lab data entry tables + v_lab_timeseries view

Revision ID: a1b2c3d4e5f7
Revises: 46644a7e7f25
Create Date: 2026-06-27 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1b2c3d4e5f7"
down_revision: str | Sequence[str] | None = "46644a7e7f25"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_VIEW_SQL = """
CREATE VIEW v_lab_timeseries AS
SELECT
    ls.sampled_at      AS time,
    sp.code            AS point_code,
    lp.code            AS param_code,
    lp.name            AS param_name,
    lp.unit            AS unit,
    lm.value           AS value,
    lp.min_limit       AS min_limit,
    lp.max_limit       AS max_limit
FROM lab_measurements lm
JOIN lab_samples ls       ON ls.id = lm.sample_id
JOIN lab_parameters lp    ON lp.id = lm.parameter_id
JOIN lab_sample_points sp ON sp.id = ls.sample_point_id
WHERE lm.value IS NOT NULL
"""


def upgrade() -> None:
    op.create_table(
        "lab_parameters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("unit", sa.String(length=50), nullable=False, server_default=""),
        sa.Column("category", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("min_limit", sa.Float(), nullable=True),
        sa.Column("max_limit", sa.Float(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("approved", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("mirror_to_tag_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["mirror_to_tag_id"], ["tags.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_table(
        "lab_sample_points",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("approved", sa.Boolean(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_table(
        "lab_samples",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sample_point_id", sa.Integer(), nullable=False),
        sa.Column("sampled_at", sa.DateTime(), nullable=False),
        sa.Column("entered_by", sa.Integer(), nullable=False),
        sa.Column("method", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("batch_no", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["sample_point_id"], ["lab_sample_points.id"]),
        sa.ForeignKeyConstraint(["entered_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lab_samples_sampled_at", "lab_samples", ["sampled_at"])
    op.create_index("ix_lab_samples_sample_point_id", "lab_samples", ["sample_point_id"])
    op.create_table(
        "lab_measurements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sample_id", sa.Integer(), nullable=False),
        sa.Column("parameter_id", sa.Integer(), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("text_value", sa.String(length=255), nullable=True),
        sa.Column("flag", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["sample_id"], ["lab_samples.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parameter_id"], ["lab_parameters.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lab_measurements_sample_id", "lab_measurements", ["sample_id"])
    op.create_index("ix_lab_measurements_parameter_id", "lab_measurements", ["parameter_id"])
    op.execute(_VIEW_SQL)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_lab_timeseries")
    op.drop_index("ix_lab_measurements_parameter_id", table_name="lab_measurements")
    op.drop_index("ix_lab_measurements_sample_id", table_name="lab_measurements")
    op.drop_table("lab_measurements")
    op.drop_index("ix_lab_samples_sample_point_id", table_name="lab_samples")
    op.drop_index("ix_lab_samples_sampled_at", table_name="lab_samples")
    op.drop_table("lab_samples")
    op.drop_table("lab_sample_points")
    op.drop_table("lab_parameters")
