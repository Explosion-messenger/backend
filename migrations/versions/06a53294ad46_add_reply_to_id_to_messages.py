"""add reply_to_id to messages

Revision ID: 06a53294ad46
Revises: i2j3k4l5m6n7
Create Date: 2026-02-22 19:53:37.273424

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '06a53294ad46'
down_revision: Union[str, Sequence[str], None] = 'i2j3k4l5m6n7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('messages', sa.Column('reply_to_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_messages_reply_to_id', 'messages', 'messages', ['reply_to_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_messages_reply_to_id', 'messages', type_='foreignkey')
    op.drop_column('messages', 'reply_to_id')
