"""tag groups (hierarchy) + annotations + Tag.group_id

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-16 16:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tag_groups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["parent_id"], ["tag_groups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tag_groups_parent_id", "tag_groups", ["parent_id"])

    op.create_table(
        "annotations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("username", sa.String(length=100), nullable=True),
        sa.Column("ts", sa.DateTime(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_annotations_tag_id", "annotations", ["tag_id"])
    op.create_index("ix_annotations_ts", "annotations", ["ts"])

    with op.batch_alter_table("tags") as batch:
        batch.add_column(sa.Column("group_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_tags_group_id", "tag_groups", ["group_id"], ["id"], ondelete="SET NULL"
        )
    op.create_index("ix_tags_group_id", "tags", ["group_id"])


def downgrade() -> None:
    op.drop_index("ix_tags_group_id", table_name="tags")
    with op.batch_alter_table("tags") as batch:
        batch.drop_constraint("fk_tags_group_id", type_="foreignkey")
        batch.drop_column("group_id")
    op.drop_index("ix_annotations_ts", table_name="annotations")
    op.drop_index("ix_annotations_tag_id", table_name="annotations")
    op.drop_table("annotations")
    op.drop_index("ix_tag_groups_parent_id", table_name="tag_groups")
    op.drop_table("tag_groups")
