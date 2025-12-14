"""add_user_auth_tables

Revision ID: 45f51e111866
Revises: 832704312906
Create Date: 2025-12-13 14:00:00.000000

Add User and UserSubscription tables for Google OAuth authentication
and per-user podcast subscriptions.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '45f51e111866'
down_revision: Union[str, None] = '832704312906'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('google_id', sa.String(128), unique=True, nullable=False),
        sa.Column('email', sa.String(256), unique=True, nullable=False),
        sa.Column('name', sa.String(256), nullable=True),
        sa.Column('picture_url', sa.String(2048), nullable=True),
        sa.Column('is_active', sa.Boolean, default=True, nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False),
        sa.Column('last_login', sa.DateTime, nullable=True),
    )
    op.create_index('ix_users_google_id', 'users', ['google_id'])
    op.create_index('ix_users_email', 'users', ['email'])

    # Create user_subscriptions table
    op.create_table(
        'user_subscriptions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column(
            'user_id',
            sa.String(36),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False
        ),
        sa.Column(
            'podcast_id',
            sa.String(36),
            sa.ForeignKey('podcasts.id', ondelete='CASCADE'),
            nullable=False
        ),
        sa.Column('subscribed_at', sa.DateTime, nullable=False),
        sa.UniqueConstraint('user_id', 'podcast_id', name='uq_user_podcast_subscription'),
    )
    op.create_index('ix_user_subscriptions_user_id', 'user_subscriptions', ['user_id'])
    op.create_index('ix_user_subscriptions_podcast_id', 'user_subscriptions', ['podcast_id'])


def downgrade() -> None:
    op.drop_index('ix_user_subscriptions_podcast_id', 'user_subscriptions')
    op.drop_index('ix_user_subscriptions_user_id', 'user_subscriptions')
    op.drop_table('user_subscriptions')
    op.drop_index('ix_users_email', 'users')
    op.drop_index('ix_users_google_id', 'users')
    op.drop_table('users')
