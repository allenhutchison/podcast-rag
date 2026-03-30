"""add_feed_performance_indexes

Revision ID: 6f17f64a4c34
Revises: 9e9bcd1d5fb9
Create Date: 2026-03-30 20:30:12.645155

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '6f17f64a4c34'
down_revision: Union[str, None] = '9e9bcd1d5fb9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index('ix_episodes_published_metadata', 'episodes', ['published_date', 'metadata_status'], unique=False)
    op.create_index('ix_user_subscriptions_user_podcast', 'user_subscriptions', ['user_id', 'podcast_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_user_subscriptions_user_podcast', table_name='user_subscriptions')
    op.drop_index('ix_episodes_published_metadata', table_name='episodes')
