"""Add is_admin to user

Revision ID: f1a2b3c4d5e6
Revises: ad2aec42bc51
Create Date: 2026-02-19 18:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'ad2aec42bc51'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('is_admin', sa.Boolean(), nullable=True, server_default=sa.text('false')))
    # Update existing users to not be null
    op.execute("UPDATE users SET is_admin = false WHERE is_admin IS NULL")
    # Make it non-nullable if desired, but for now we'll keep it simple
    # op.alter_column('users', 'is_admin', nullable=False)


def downgrade() -> None:
    op.drop_column('users', 'is_admin')
