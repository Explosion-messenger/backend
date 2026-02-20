"""add_email_verification_and_2fa_to_user

Revision ID: 5e7836855c7f
Revises: 28ede4ec1e4a
Create Date: 2026-02-20 19:29:03.545432

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5e7836855c7f'
down_revision: Union[str, Sequence[str], None] = '28ede4ec1e4a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add columns
    op.add_column('users', sa.Column('email', sa.String(), nullable=True))
    op.add_column('users', sa.Column('is_verified', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('users', sa.Column('otp_secret', sa.String(), nullable=True))
    op.add_column('users', sa.Column('is_2fa_enabled', sa.Boolean(), nullable=True, server_default='false'))
    
    # Create index for email
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    
    # Update existing users to be verified (optional, but good for migration)
    op.execute("UPDATE users SET is_verified = true WHERE is_verified IS NULL")
    op.execute("UPDATE users SET is_2fa_enabled = false WHERE is_2fa_enabled IS NULL")

def downgrade() -> None:
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_column('users', 'is_2fa_enabled')
    op.drop_column('users', 'otp_secret')
    op.drop_column('users', 'is_verified')
    op.drop_column('users', 'email')
