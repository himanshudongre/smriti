"""Add project_root to repos.

Revision ID: d1e2f3a4b5c6
Revises: c0db5e90f1a2
Create Date: 2026-05-04 03:00:00.000000

"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "d1e2f3a4b5c6"
down_revision = "c0db5e90f1a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "repos",
        sa.Column("project_root", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("repos", "project_root")
