"""add_ai_email_content_column

Revision ID: b6be3bac19d4
Revises: b2c3d4e5f6a7
Create Date: 2025-12-22 09:29:02.892647

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b6be3bac19d4'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'episodes',
        sa.Column('ai_email_content', sa.JSON(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('episodes', 'ai_email_content')
