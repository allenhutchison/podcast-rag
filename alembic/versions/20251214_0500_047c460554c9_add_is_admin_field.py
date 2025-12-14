"""add_is_admin_field

Revision ID: 047c460554c9
Revises: 45f51e111866
Create Date: 2025-12-14 05:00:00.000000

Add is_admin field to users table for admin access control.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '047c460554c9'
down_revision: Union[str, None] = '45f51e111866'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('is_admin', sa.Boolean, server_default=sa.text('0'), nullable=False)
    )
    op.create_index('ix_users_is_admin', 'users', ['is_admin'])


def downgrade() -> None:
    op.drop_index('ix_users_is_admin', 'users')
    op.drop_column('users', 'is_admin')
