"""Add work_trees table.

Revision ID: b9cadbef0102
Revises: a8b9cadbef01
Create Date: 2026-05-04 01:00:00.000000

"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "b9cadbef0102"
down_revision = "a8b9cadbef01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "work_trees",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "repo_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("repos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("agent", sa.String(100), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("branch_name", sa.String(255), nullable=False),
        sa.Column("base_commit_sha", sa.String(64), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_work_trees_repo", "work_trees", ["repo_id"], unique=False)
    op.create_index(
        "idx_work_trees_active",
        "work_trees",
        ["repo_id", "status"],
        unique=False,
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index("idx_work_trees_active", table_name="work_trees")
    op.drop_index("idx_work_trees_repo", table_name="work_trees")
    op.drop_table("work_trees")
