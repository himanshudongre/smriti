"""Add branch_disposition column to chat_sessions.

Revision ID: f7a8b9cadbef
Revises: e6f7a8b9cadb
Create Date: 2026-04-13 01:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "f7a8b9cadbef"
down_revision = "e6f7a8b9cadb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_sessions",
        sa.Column("branch_disposition", sa.String(20), server_default="active"),
    )


def downgrade() -> None:
    op.drop_column("chat_sessions", "branch_disposition")
