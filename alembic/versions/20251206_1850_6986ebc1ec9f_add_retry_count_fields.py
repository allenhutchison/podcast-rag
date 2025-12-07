"""add_retry_count_fields

Revision ID: 6986ebc1ec9f
Revises: 001
Create Date: 2025-12-06 18:50:47.346056

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6986ebc1ec9f'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add retry count columns for pipeline mode
    op.add_column(
        'episodes',
        sa.Column('transcript_retry_count', sa.Integer(), nullable=False, server_default='0')
    )
    op.add_column(
        'episodes',
        sa.Column('metadata_retry_count', sa.Integer(), nullable=False, server_default='0')
    )
    op.add_column(
        'episodes',
        sa.Column('indexing_retry_count', sa.Integer(), nullable=False, server_default='0')
    )


def downgrade() -> None:
    op.drop_column('episodes', 'indexing_retry_count')
    op.drop_column('episodes', 'metadata_retry_count')
    op.drop_column('episodes', 'transcript_retry_count')
