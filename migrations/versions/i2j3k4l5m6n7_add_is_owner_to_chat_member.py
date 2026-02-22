"""add_is_owner_to_chat_member

Revision ID: i2j3k4l5m6n7
Revises: e6f7g8h9i0j1
Create Date: 2026-02-22 15:52:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'i2j3k4l5m6n7'
down_revision: Union[str, Sequence[str], None] = 'e6f7g8h9i0j1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('chat_members', sa.Column('is_owner', sa.Boolean(), nullable=True, server_default=sa.text('false')))
    # Set existing admins as owners for now (or at least one of them)
    # But since we just added is_admin, and the owner was the only admin, we can sync them.
    op.execute("UPDATE chat_members SET is_owner = true WHERE is_admin = true")
    op.execute("UPDATE chat_members SET is_owner = false WHERE is_owner IS NULL")


def downgrade() -> None:
    op.drop_column('chat_members', 'is_owner')
