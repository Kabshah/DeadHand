"""otp_attempt_ip_address

Revision ID: e6dc275f54ab
Revises: 0001
Create Date: 2026-09-13 05:37:31.493305

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e6dc275f54ab'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('otp_attempts', sa.Column('ip_address', sa.String(length=45), nullable=True))
    op.add_column('users', sa.Column('created_ip', sa.String(length=45), nullable=True))
    op.create_index('ix_users_created_ip', 'users', ['created_ip'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_users_created_ip', table_name='users')
    op.drop_column('users', 'created_ip')
    op.drop_column('otp_attempts', 'ip_address')


