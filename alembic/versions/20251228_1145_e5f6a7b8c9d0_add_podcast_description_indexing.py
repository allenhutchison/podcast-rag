"""add_podcast_description_indexing

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2025-12-28 11:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add description File Search tracking fields to podcasts table
    op.add_column(
        'podcasts',
        sa.Column('description_file_search_status', sa.String(32), nullable=False, server_default='pending')
    )
    op.add_column(
        'podcasts',
        sa.Column('description_file_search_error', sa.Text(), nullable=True)
    )
    op.add_column(
        'podcasts',
        sa.Column('description_file_search_resource_name', sa.String(512), nullable=True)
    )
    op.add_column(
        'podcasts',
        sa.Column('description_file_search_display_name', sa.String(512), nullable=True)
    )
    op.add_column(
        'podcasts',
        sa.Column('description_file_search_uploaded_at', sa.DateTime(), nullable=True)
    )

    # Add index for efficient status queries
    op.create_index(
        'ix_podcasts_description_file_search_status',
        'podcasts',
        ['description_file_search_status']
    )


def downgrade() -> None:
    op.drop_index('ix_podcasts_description_file_search_status', table_name='podcasts')
    op.drop_column('podcasts', 'description_file_search_uploaded_at')
    op.drop_column('podcasts', 'description_file_search_display_name')
    op.drop_column('podcasts', 'description_file_search_resource_name')
    op.drop_column('podcasts', 'description_file_search_error')
    op.drop_column('podcasts', 'description_file_search_status')
