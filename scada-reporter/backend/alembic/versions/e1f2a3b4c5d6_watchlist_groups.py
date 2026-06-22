"""watchlist groups + members

Revision ID: e1f2a3b4c5d6
Revises: d5e6f7a8b9c0
"""

import sqlalchemy as sa

from alembic import op

revision = "e1f2a3b4c5d6"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "watchlist_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("user_id", "name", name="uc_wlgroup_user_name"),
    )
    op.create_index("ix_watchlist_groups_user_id", "watchlist_groups", ["user_id"])
    op.create_table(
        "watchlist_group_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "group_id",
            sa.Integer(),
            sa.ForeignKey("watchlist_groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tag_id", sa.Integer(), sa.ForeignKey("tags.id", ondelete="CASCADE"), nullable=False
        ),
        sa.UniqueConstraint("group_id", "tag_id", name="uc_wlmember_group_tag"),
    )
    op.create_index("ix_watchlist_group_members_group_id", "watchlist_group_members", ["group_id"])


def downgrade() -> None:
    op.drop_index("ix_watchlist_group_members_group_id", table_name="watchlist_group_members")
    op.drop_table("watchlist_group_members")
    op.drop_index("ix_watchlist_groups_user_id", table_name="watchlist_groups")
    op.drop_table("watchlist_groups")
