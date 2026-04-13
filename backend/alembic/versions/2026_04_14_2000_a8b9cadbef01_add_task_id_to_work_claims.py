"""Add task_id column to work_claims.

Allows claims to reference a specific structured task by its id field,
enabling precise collision detection when multiple agents start
near-simultaneously.

Revision ID: a8b9cadbef01
Revises: f7a8b9cadbef
Create Date: 2026-04-14 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "a8b9cadbef01"
down_revision = "f7a8b9cadbef"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "work_claims",
        sa.Column("task_id", sa.String(100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("work_claims", "task_id")
