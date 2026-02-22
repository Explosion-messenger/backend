"""add_is_admin_to_chat_member

Revision ID: e6f7g8h9i0j1
Revises: 5e7836855c7f
Create Date: 2026-02-22 15:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e6f7g8h9i0j1'
down_revision: Union[str, Sequence[str], None] = '5e7836855c7f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('chat_members', sa.Column('is_admin', sa.Boolean(), nullable=True, server_default=sa.text('false')))
    op.execute("UPDATE chat_members SET is_admin = false WHERE is_admin IS NULL")


def downgrade() -> None:
    op.drop_column('chat_members', 'is_admin')
