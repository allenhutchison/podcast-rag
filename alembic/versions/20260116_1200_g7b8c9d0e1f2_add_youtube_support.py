"""add_youtube_support

Revision ID: g7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-01-16 12:00:00.000000

Add source_type discriminator and YouTube-specific fields to Podcast and Episode tables.
This enables YouTube channel subscriptions alongside existing RSS podcast support.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'g7b8c9d0e1f2'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Podcast table additions
    op.add_column(
        'podcasts',
        sa.Column('source_type', sa.String(32), nullable=False, server_default='rss')
    )
    op.add_column(
        'podcasts',
        sa.Column('youtube_channel_id', sa.String(64), nullable=True)
    )
    op.add_column(
        'podcasts',
        sa.Column('youtube_channel_url', sa.String(2048), nullable=True)
    )
    op.add_column(
        'podcasts',
        sa.Column('youtube_handle', sa.String(256), nullable=True)
    )
    op.add_column(
        'podcasts',
        sa.Column('youtube_playlist_id', sa.String(64), nullable=True)
    )
    op.add_column(
        'podcasts',
        sa.Column('youtube_subscriber_count', sa.Integer(), nullable=True)
    )
    op.add_column(
        'podcasts',
        sa.Column('youtube_video_count', sa.Integer(), nullable=True)
    )

    # Podcast indexes
    op.create_index('ix_podcasts_source_type', 'podcasts', ['source_type'])
    op.create_index('ix_podcasts_youtube_channel_id', 'podcasts', ['youtube_channel_id'])

    # Episode table additions
    op.add_column(
        'episodes',
        sa.Column('source_type', sa.String(32), nullable=False, server_default='podcast_episode')
    )
    op.add_column(
        'episodes',
        sa.Column('youtube_video_id', sa.String(16), nullable=True)
    )
    op.add_column(
        'episodes',
        sa.Column('youtube_video_url', sa.String(2048), nullable=True)
    )
    op.add_column(
        'episodes',
        sa.Column('youtube_view_count', sa.Integer(), nullable=True)
    )
    op.add_column(
        'episodes',
        sa.Column('youtube_like_count', sa.Integer(), nullable=True)
    )
    op.add_column(
        'episodes',
        sa.Column('youtube_captions_available', sa.Boolean(), nullable=True)
    )
    op.add_column(
        'episodes',
        sa.Column('youtube_captions_language', sa.String(16), nullable=True)
    )
    op.add_column(
        'episodes',
        sa.Column('transcript_source', sa.String(32), nullable=True)
    )

    # Episode indexes
    op.create_index('ix_episodes_source_type', 'episodes', ['source_type'])
    op.create_index('ix_episodes_youtube_video_id', 'episodes', ['youtube_video_id'])


def downgrade() -> None:
    # Episode indexes
    op.drop_index('ix_episodes_youtube_video_id', table_name='episodes')
    op.drop_index('ix_episodes_source_type', table_name='episodes')

    # Episode columns
    op.drop_column('episodes', 'transcript_source')
    op.drop_column('episodes', 'youtube_captions_language')
    op.drop_column('episodes', 'youtube_captions_available')
    op.drop_column('episodes', 'youtube_like_count')
    op.drop_column('episodes', 'youtube_view_count')
    op.drop_column('episodes', 'youtube_video_url')
    op.drop_column('episodes', 'youtube_video_id')
    op.drop_column('episodes', 'source_type')

    # Podcast indexes
    op.drop_index('ix_podcasts_youtube_channel_id', table_name='podcasts')
    op.drop_index('ix_podcasts_source_type', table_name='podcasts')

    # Podcast columns
    op.drop_column('podcasts', 'youtube_video_count')
    op.drop_column('podcasts', 'youtube_subscriber_count')
    op.drop_column('podcasts', 'youtube_playlist_id')
    op.drop_column('podcasts', 'youtube_handle')
    op.drop_column('podcasts', 'youtube_channel_url')
    op.drop_column('podcasts', 'youtube_channel_id')
    op.drop_column('podcasts', 'source_type')
