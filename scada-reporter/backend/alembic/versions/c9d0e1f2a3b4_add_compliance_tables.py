"""add compliance tables

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-06-28 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: str | None = "b8c9d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "compliance_permits",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("facility_name", sa.String(length=255), nullable=True),
        sa.Column("authority", sa.String(length=255), nullable=True),
        sa.Column("permit_number", sa.String(length=128), nullable=True),
        sa.Column("valid_from", sa.DateTime(), nullable=True),
        sa.Column("valid_to", sa.DateTime(), nullable=True),
        sa.Column("report_frequency", sa.String(length=32), nullable=True),
        sa.Column("report_cron", sa.String(length=128), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "compliance_discharge_points",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("permit_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("lab_sample_point_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["permit_id"], ["compliance_permits.id"]),
        sa.ForeignKeyConstraint(["lab_sample_point_id"], ["lab_sample_points.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_compliance_discharge_points_permit_id",
        "compliance_discharge_points",
        ["permit_id"],
    )

    op.create_table(
        "compliance_parameters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("permit_id", sa.Integer(), nullable=False),
        sa.Column("discharge_point_id", sa.Integer(), nullable=False),
        sa.Column("parameter_name", sa.String(length=255), nullable=False),
        sa.Column("unit", sa.String(length=64), nullable=True),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=True),
        sa.Column("lab_parameter_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["permit_id"], ["compliance_permits.id"]),
        sa.ForeignKeyConstraint(["discharge_point_id"], ["compliance_discharge_points.id"]),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"]),
        sa.ForeignKeyConstraint(["lab_parameter_id"], ["lab_parameters.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_compliance_parameters_permit_id",
        "compliance_parameters",
        ["permit_id"],
    )
    op.create_index(
        "ix_compliance_parameters_discharge_point_id",
        "compliance_parameters",
        ["discharge_point_id"],
    )

    op.create_table(
        "compliance_limits",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("parameter_id", sa.Integer(), nullable=False),
        sa.Column("limit_type", sa.String(length=32), nullable=False),
        sa.Column("min_value", sa.Float(), nullable=True),
        sa.Column("max_value", sa.Float(), nullable=True),
        sa.Column("aggregation", sa.String(length=32), nullable=False),
        sa.Column("window", sa.String(length=64), nullable=True),
        sa.Column("sample_frequency", sa.String(length=64), nullable=True),
        sa.Column("severity", sa.String(length=32), nullable=True),
        sa.Column("requires_explanation", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["parameter_id"], ["compliance_parameters.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_compliance_limits_parameter_id",
        "compliance_limits",
        ["parameter_id"],
    )

    op.create_table(
        "compliance_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("permit_id", sa.Integer(), nullable=False),
        sa.Column("parameter_id", sa.Integer(), nullable=False),
        sa.Column("limit_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=True),
        sa.Column("period_start", sa.DateTime(), nullable=False),
        sa.Column("period_end", sa.DateTime(), nullable=False),
        sa.Column("observed_value", sa.Float(), nullable=True),
        sa.Column("limit_value", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("event_key", sa.String(length=128), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(), nullable=True),
        sa.Column("acknowledged_by", sa.Integer(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_by", sa.Integer(), nullable=True),
        sa.Column("waived_at", sa.DateTime(), nullable=True),
        sa.Column("waived_by", sa.Integer(), nullable=True),
        sa.Column("waive_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["permit_id"], ["compliance_permits.id"]),
        sa.ForeignKeyConstraint(["parameter_id"], ["compliance_parameters.id"]),
        sa.ForeignKeyConstraint(["limit_id"], ["compliance_limits.id"]),
        sa.ForeignKeyConstraint(["acknowledged_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["waived_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_key", name="uq_compliance_events_event_key"),
    )
    op.create_index("ix_compliance_events_status", "compliance_events", ["status"])
    op.create_index("ix_compliance_events_period_start", "compliance_events", ["period_start"])
    op.create_index("ix_compliance_events_period_end", "compliance_events", ["period_end"])
    op.create_index("ix_compliance_events_permit_id", "compliance_events", ["permit_id"])
    op.create_index("ix_compliance_events_parameter_id", "compliance_events", ["parameter_id"])
    op.create_index("ix_compliance_events_limit_id", "compliance_events", ["limit_id"])
    op.create_index("ix_compliance_events_resolved_at", "compliance_events", ["resolved_at"])

    op.create_table(
        "compliance_event_notes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["event_id"], ["compliance_events.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_compliance_event_notes_event_id",
        "compliance_event_notes",
        ["event_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_compliance_event_notes_event_id", table_name="compliance_event_notes")
    op.drop_table("compliance_event_notes")

    op.drop_index("ix_compliance_events_resolved_at", table_name="compliance_events")
    op.drop_index("ix_compliance_events_limit_id", table_name="compliance_events")
    op.drop_index("ix_compliance_events_parameter_id", table_name="compliance_events")
    op.drop_index("ix_compliance_events_permit_id", table_name="compliance_events")
    op.drop_index("ix_compliance_events_period_end", table_name="compliance_events")
    op.drop_index("ix_compliance_events_period_start", table_name="compliance_events")
    op.drop_index("ix_compliance_events_status", table_name="compliance_events")
    op.drop_table("compliance_events")

    op.drop_index("ix_compliance_limits_parameter_id", table_name="compliance_limits")
    op.drop_table("compliance_limits")

    op.drop_index(
        "ix_compliance_parameters_discharge_point_id",
        table_name="compliance_parameters",
    )
    op.drop_index("ix_compliance_parameters_permit_id", table_name="compliance_parameters")
    op.drop_table("compliance_parameters")

    op.drop_index(
        "ix_compliance_discharge_points_permit_id",
        table_name="compliance_discharge_points",
    )
    op.drop_table("compliance_discharge_points")

    op.drop_table("compliance_permits")
