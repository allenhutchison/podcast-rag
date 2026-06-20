"""add_briefing_audio_fields

Revision ID: a1b2c3d4e5f6
Revises: 6f17f64a4c34
Create Date: 2026-06-19 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '6f17f64a4c34'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('daily_briefings', sa.Column('audio_data', sa.LargeBinary(), nullable=True))
    op.add_column('daily_briefings', sa.Column('audio_mime_type', sa.String(length=64), nullable=True))
    op.add_column('daily_briefings', sa.Column('audio_status', sa.String(length=20), nullable=True))
    op.add_column('daily_briefings', sa.Column('audio_duration_sec', sa.Integer(), nullable=True))
    op.add_column('daily_briefings', sa.Column('audio_generated_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('daily_briefings', 'audio_generated_at')
    op.drop_column('daily_briefings', 'audio_duration_sec')
    op.drop_column('daily_briefings', 'audio_status')
    op.drop_column('daily_briefings', 'audio_mime_type')
    op.drop_column('daily_briefings', 'audio_data')