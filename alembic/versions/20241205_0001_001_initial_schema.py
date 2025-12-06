"""Initial schema for podcasts and episodes

Revision ID: 001
Revises:
Create Date: 2024-12-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create podcasts table
    op.create_table(
        'podcasts',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('feed_url', sa.String(2048), unique=True, nullable=False),
        sa.Column('website_url', sa.String(2048), nullable=True),
        sa.Column('title', sa.String(512), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('author', sa.String(512), nullable=True),
        sa.Column('language', sa.String(32), nullable=True),
        sa.Column('itunes_id', sa.String(64), nullable=True),
        sa.Column('itunes_author', sa.String(512), nullable=True),
        sa.Column('itunes_category', sa.String(256), nullable=True),
        sa.Column('itunes_subcategory', sa.String(256), nullable=True),
        sa.Column('itunes_explicit', sa.Boolean, nullable=True),
        sa.Column('itunes_type', sa.String(32), nullable=True),
        sa.Column('image_url', sa.String(2048), nullable=True),
        sa.Column('image_local_path', sa.String(1024), nullable=True),
        sa.Column('is_subscribed', sa.Boolean, default=True),
        sa.Column('last_checked', sa.DateTime, nullable=True),
        sa.Column('last_new_episode', sa.DateTime, nullable=True),
        sa.Column('check_frequency_hours', sa.Integer, default=24),
        sa.Column('local_directory', sa.String(1024), nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False),
    )
    op.create_index('ix_podcasts_feed_url', 'podcasts', ['feed_url'])

    # Create episodes table
    op.create_table(
        'episodes',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('podcast_id', sa.String(36), sa.ForeignKey('podcasts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('guid', sa.String(2048), nullable=False),
        sa.Column('title', sa.String(512), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('link', sa.String(2048), nullable=True),
        sa.Column('published_date', sa.DateTime, nullable=True),
        sa.Column('duration_seconds', sa.Integer, nullable=True),
        sa.Column('episode_number', sa.String(32), nullable=True),
        sa.Column('season_number', sa.Integer, nullable=True),
        sa.Column('episode_type', sa.String(32), nullable=True),
        sa.Column('itunes_title', sa.String(512), nullable=True),
        sa.Column('itunes_episode', sa.String(32), nullable=True),
        sa.Column('itunes_season', sa.Integer, nullable=True),
        sa.Column('itunes_explicit', sa.Boolean, nullable=True),
        sa.Column('itunes_duration', sa.String(32), nullable=True),
        sa.Column('enclosure_url', sa.String(2048), nullable=False),
        sa.Column('enclosure_type', sa.String(64), nullable=False),
        sa.Column('enclosure_length', sa.Integer, nullable=True),
        sa.Column('download_status', sa.String(32), default='pending'),
        sa.Column('download_error', sa.Text, nullable=True),
        sa.Column('downloaded_at', sa.DateTime, nullable=True),
        sa.Column('local_file_path', sa.String(1024), nullable=True),
        sa.Column('file_size_bytes', sa.Integer, nullable=True),
        sa.Column('file_hash', sa.String(64), nullable=True),
        sa.Column('transcript_status', sa.String(32), default='pending'),
        sa.Column('transcript_error', sa.Text, nullable=True),
        sa.Column('transcript_path', sa.String(1024), nullable=True),
        sa.Column('transcribed_at', sa.DateTime, nullable=True),
        sa.Column('metadata_status', sa.String(32), default='pending'),
        sa.Column('metadata_error', sa.Text, nullable=True),
        sa.Column('metadata_path', sa.String(1024), nullable=True),
        sa.Column('ai_summary', sa.Text, nullable=True),
        sa.Column('ai_keywords', sa.JSON, nullable=True),
        sa.Column('ai_hosts', sa.JSON, nullable=True),
        sa.Column('ai_guests', sa.JSON, nullable=True),
        sa.Column('file_search_status', sa.String(32), default='pending'),
        sa.Column('file_search_error', sa.Text, nullable=True),
        sa.Column('file_search_resource_name', sa.String(512), nullable=True),
        sa.Column('file_search_display_name', sa.String(512), nullable=True),
        sa.Column('file_search_uploaded_at', sa.DateTime, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False),
    )
    op.create_index('ix_episodes_podcast_id', 'episodes', ['podcast_id'])
    op.create_index('ix_episodes_download_status', 'episodes', ['download_status'])
    op.create_index('ix_episodes_transcript_status', 'episodes', ['transcript_status'])
    op.create_index('ix_episodes_file_search_status', 'episodes', ['file_search_status'])
    op.create_index('ix_episodes_published_date', 'episodes', ['published_date'])
    op.create_unique_constraint('uq_episode_podcast_guid', 'episodes', ['podcast_id', 'guid'])


def downgrade() -> None:
    op.drop_table('episodes')
    op.drop_table('podcasts')
