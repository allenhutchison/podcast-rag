"""add_daily_briefings_table

Revision ID: 9e9bcd1d5fb9
Revises: f6a7b8c9d0e1
Create Date: 2026-03-28 18:59:00.688825

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9e9bcd1d5fb9'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('daily_briefings',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('briefing_date', sa.Date(), nullable=False),
    sa.Column('headline', sa.String(length=256), nullable=False),
    sa.Column('briefing_text', sa.Text(), nullable=False),
    sa.Column('key_themes', sa.JSON(), nullable=False),
    sa.Column('episode_highlights', sa.JSON(), nullable=False),
    sa.Column('connection_insight', sa.Text(), nullable=True),
    sa.Column('episode_count', sa.Integer(), nullable=False),
    sa.Column('episode_ids', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'briefing_date', name='uq_user_briefing_date')
    )
    op.create_index('ix_daily_briefings_user_date', 'daily_briefings', ['user_id', 'briefing_date'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_daily_briefings_user_date', table_name='daily_briefings')
    op.drop_table('daily_briefings')
