"""Add worktree_id FK to work_claims.

Revision ID: c0db5e90f1a2
Revises: b9cadbef0102
Create Date: 2026-05-04 02:00:00.000000

"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "c0db5e90f1a2"
down_revision = "b9cadbef0102"
branch_labels = None
depends_on = None

WORKTREE_FK_NAME = "fk_work_claims_worktree_id_work_trees"
WORKTREE_INDEX_NAME = "idx_work_claims_worktree"


def upgrade() -> None:
    with op.batch_alter_table("work_claims") as batch_op:
        batch_op.add_column(
            sa.Column(
                "worktree_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
            ),
        )
        batch_op.create_foreign_key(
            WORKTREE_FK_NAME,
            "work_trees",
            ["worktree_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(
        WORKTREE_INDEX_NAME,
        "work_claims",
        ["worktree_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(WORKTREE_INDEX_NAME, table_name="work_claims")
    with op.batch_alter_table("work_claims") as batch_op:
        batch_op.drop_constraint(WORKTREE_FK_NAME, type_="foreignkey")
        batch_op.drop_column("worktree_id")
