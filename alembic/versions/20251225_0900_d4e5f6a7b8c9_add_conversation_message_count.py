"""Add message_count column to conversations table.

Denormalized count to avoid N+1 queries when listing conversations.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2025-12-25 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add message_count column with default 0
    op.add_column(
        'conversations',
        sa.Column('message_count', sa.Integer(), nullable=False, server_default='0')
    )

    # Backfill existing conversations with actual message counts
    op.execute("""
        UPDATE conversations
        SET message_count = (
            SELECT COUNT(*)
            FROM chat_messages
            WHERE chat_messages.conversation_id = conversations.id
        )
    """)


def downgrade() -> None:
    op.drop_column('conversations', 'message_count')
