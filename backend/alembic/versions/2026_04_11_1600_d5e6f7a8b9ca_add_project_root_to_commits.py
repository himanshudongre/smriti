"""add_project_root_to_commits

Revision ID: d5e6f7a8b9ca
Revises: c4d5e6f7a8b9
Create Date: 2026-04-11 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5e6f7a8b9ca'
down_revision: Union[str, None] = 'c4d5e6f7a8b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'commits',
        sa.Column('project_root', sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('commits', 'project_root')
