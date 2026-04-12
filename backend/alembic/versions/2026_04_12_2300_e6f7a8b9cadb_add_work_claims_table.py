"""Add work_claims table for pre-work intent visibility.

Revision ID: e6f7a8b9cadb
Revises: d5e6f7a8b9ca
Create Date: 2026-04-12 23:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "e6f7a8b9cadb"
down_revision = "d5e6f7a8b9ca"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "work_claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "repo_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("repos.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chat_sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("agent", sa.String(100), nullable=False),
        sa.Column("branch_name", sa.String(255), server_default="main"),
        sa.Column(
            "base_commit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("commits.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("intent_type", sa.String(20), server_default="implement"),
        sa.Column("status", sa.String(20), server_default="active"),
        sa.Column(
            "claimed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("work_claims")
