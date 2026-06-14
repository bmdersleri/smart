"""initial

Revision ID: 97421fc62374
Revises:
Create Date: 2026-06-14 17:56:31.135085

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "97421fc62374"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=150), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column(
            "full_name", sa.String(length=255), nullable=False, server_default=""
        ),
        sa.Column(
            "role", sa.String(length=50), nullable=False, server_default="operator"
        ),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )

    op.create_table(
        "tags",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("node_id", sa.String(length=512), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("unit", sa.String(length=50), nullable=False, server_default=""),
        sa.Column("channel", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("device", sa.String(length=255), nullable=False, server_default=""),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("node_id"),
    )

    op.create_table(
        "tag_readings",
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column(
            "quality", sa.Integer(), nullable=False, server_default=sa.text("192")
        ),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("tag_id", "timestamp"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], name="fk_tag_readings_tag_id"),
    )
    op.create_index(
        "idx_tag_readings_tag_ts", "tag_readings", ["tag_id", sa.text("timestamp DESC")]
    )


def downgrade() -> None:
    op.drop_index("idx_tag_readings_tag_ts", table_name="tag_readings")
    op.drop_table("tag_readings")
    op.drop_table("tags")
    op.drop_table("users")
