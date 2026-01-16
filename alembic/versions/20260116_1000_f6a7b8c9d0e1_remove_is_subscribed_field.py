"""remove_is_subscribed_field

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-01-16 10:00:00.000000

Remove the legacy is_subscribed field from podcasts table.
Subscription status is now determined by UserSubscription entries.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('podcasts', 'is_subscribed')


def downgrade() -> None:
    op.add_column(
        'podcasts',
        sa.Column('is_subscribed', sa.Boolean(), server_default=sa.text('TRUE'), nullable=False)
    )
