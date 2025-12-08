"""add_transcript_text_column

Revision ID: 832704312906
Revises: 6986ebc1ec9f
Create Date: 2025-12-07 19:30:00.000000

Add columns to store transcript text and MP3 metadata directly in the database,
eliminating the need for separate _transcription.txt and _metadata.json files.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '832704312906'
down_revision: Union[str, None] = '6986ebc1ec9f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add transcript text column for storing full transcript content
    op.add_column(
        'episodes',
        sa.Column('transcript_text', sa.Text(), nullable=True)
    )
    # Add MP3 metadata columns
    op.add_column(
        'episodes',
        sa.Column('mp3_artist', sa.String(512), nullable=True)
    )
    op.add_column(
        'episodes',
        sa.Column('mp3_album', sa.String(512), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('episodes', 'mp3_album')
    op.drop_column('episodes', 'mp3_artist')
    op.drop_column('episodes', 'transcript_text')
