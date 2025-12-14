"""add_user_timezone_and_digest_hour

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2025-12-14 07:00:00.000000

Add per-user timezone and email digest delivery hour preferences.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add timezone column (IANA timezone string, e.g., "America/New_York")
    # Nullable - will be auto-detected from browser on first settings visit
    op.add_column(
        'users',
        sa.Column('timezone', sa.String(64), nullable=True)
    )
    # Add email_digest_hour column (0-23, default 8 for 8 AM)
    op.add_column(
        'users',
        sa.Column('email_digest_hour', sa.Integer, server_default=sa.text('8'), nullable=False)
    )


def downgrade() -> None:
    op.drop_column('users', 'email_digest_hour')
    op.drop_column('users', 'timezone')
