"""Add cascade deletes to foreign keys

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-02-19 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add ON DELETE CASCADE / SET NULL to foreign keys."""

    # chat_members.chat_id -> CASCADE
    op.drop_constraint('chat_members_chat_id_fkey', 'chat_members', type_='foreignkey')
    op.create_foreign_key('chat_members_chat_id_fkey', 'chat_members', 'chats',
                          ['chat_id'], ['id'], ondelete='CASCADE')

    # chat_members.user_id -> CASCADE
    op.drop_constraint('chat_members_user_id_fkey', 'chat_members', type_='foreignkey')
    op.create_foreign_key('chat_members_user_id_fkey', 'chat_members', 'users',
                          ['user_id'], ['id'], ondelete='CASCADE')

    # messages.chat_id -> CASCADE
    op.drop_constraint('messages_chat_id_fkey', 'messages', type_='foreignkey')
    op.create_foreign_key('messages_chat_id_fkey', 'messages', 'chats',
                          ['chat_id'], ['id'], ondelete='CASCADE')

    # messages.sender_id -> CASCADE
    op.drop_constraint('messages_sender_id_fkey', 'messages', type_='foreignkey')
    op.create_foreign_key('messages_sender_id_fkey', 'messages', 'users',
                          ['sender_id'], ['id'], ondelete='CASCADE')

    # messages.file_id -> SET NULL
    op.drop_constraint('messages_file_id_fkey', 'messages', type_='foreignkey')
    op.create_foreign_key('messages_file_id_fkey', 'messages', 'files',
                          ['file_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    """Remove ON DELETE rules from foreign keys (revert to default NO ACTION)."""

    op.drop_constraint('messages_file_id_fkey', 'messages', type_='foreignkey')
    op.create_foreign_key('messages_file_id_fkey', 'messages', 'files',
                          ['file_id'], ['id'])

    op.drop_constraint('messages_sender_id_fkey', 'messages', type_='foreignkey')
    op.create_foreign_key('messages_sender_id_fkey', 'messages', 'users',
                          ['sender_id'], ['id'])

    op.drop_constraint('messages_chat_id_fkey', 'messages', type_='foreignkey')
    op.create_foreign_key('messages_chat_id_fkey', 'messages', 'chats',
                          ['chat_id'], ['id'])

    op.drop_constraint('chat_members_user_id_fkey', 'chat_members', type_='foreignkey')
    op.create_foreign_key('chat_members_user_id_fkey', 'chat_members', 'users',
                          ['user_id'], ['id'])

    op.drop_constraint('chat_members_chat_id_fkey', 'chat_members', type_='foreignkey')
    op.create_foreign_key('chat_members_chat_id_fkey', 'chat_members', 'chats',
                          ['chat_id'], ['id'])
