"""add_fork_fields_to_chat_sessions

Revision ID: a1b2c3d4e5f6
Revises: 8473b83ba7a7
Create Date: 2026-03-21 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '8473b83ba7a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'chat_sessions',
        sa.Column('forked_from_checkpoint_id', sa.UUID(), nullable=True),
    )
    op.add_column(
        'chat_sessions',
        sa.Column('branch_name', sa.String(length=255), nullable=False, server_default='main'),
    )
    op.create_foreign_key(
        'fk_chat_sessions_forked_from_checkpoint_id',
        'chat_sessions', 'commits',
        ['forked_from_checkpoint_id'], ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_chat_sessions_forked_from_checkpoint_id', 'chat_sessions', type_='foreignkey')
    op.drop_column('chat_sessions', 'branch_name')
    op.drop_column('chat_sessions', 'forked_from_checkpoint_id')
