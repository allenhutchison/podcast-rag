"""add_email_digest_preferences

Revision ID: a1b2c3d4e5f6
Revises: 047c460554c9
Create Date: 2025-12-14 06:00:00.000000

Add email digest preference fields to users table for daily email digests.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '047c460554c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add email_digest_enabled column (default False for opt-in)
    op.add_column(
        'users',
        sa.Column('email_digest_enabled', sa.Boolean, server_default=sa.text('0'), nullable=False)
    )
    # Add last_email_digest_sent column to track when digest was last sent
    op.add_column(
        'users',
        sa.Column('last_email_digest_sent', sa.DateTime, nullable=True)
    )


def downgrade() -> None:
    op.drop_column('users', 'last_email_digest_sent')
    op.drop_column('users', 'email_digest_enabled')
