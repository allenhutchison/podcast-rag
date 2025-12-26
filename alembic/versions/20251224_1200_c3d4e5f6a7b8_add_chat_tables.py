"""add_chat_tables

Revision ID: c3d4e5f6a7b8
Revises: b6be3bac19d4
Create Date: 2025-12-24 12:00:00.000000

Add Conversation and ChatMessage tables for persistent chat history.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b6be3bac19d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create conversations table
    op.create_table(
        'conversations',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column(
            'user_id',
            sa.String(36),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False
        ),
        sa.Column('title', sa.String(256), nullable=True),
        sa.Column('scope', sa.String(32), nullable=False),
        sa.Column(
            'podcast_id',
            sa.String(36),
            sa.ForeignKey('podcasts.id', ondelete='SET NULL'),
            nullable=True
        ),
        sa.Column(
            'episode_id',
            sa.String(36),
            sa.ForeignKey('episodes.id', ondelete='SET NULL'),
            nullable=True
        ),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False),
    )
    op.create_index('ix_conversations_user_id', 'conversations', ['user_id'])
    op.create_index('ix_conversations_updated_at', 'conversations', ['updated_at'])

    # Create chat_messages table
    op.create_table(
        'chat_messages',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column(
            'conversation_id',
            sa.String(36),
            sa.ForeignKey('conversations.id', ondelete='CASCADE'),
            nullable=False
        ),
        sa.Column('role', sa.String(16), nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('citations', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
    )
    op.create_index('ix_chat_messages_conversation_id', 'chat_messages', ['conversation_id'])
    op.create_index('ix_chat_messages_created_at', 'chat_messages', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_chat_messages_created_at', 'chat_messages')
    op.drop_index('ix_chat_messages_conversation_id', 'chat_messages')
    op.drop_table('chat_messages')
    op.drop_index('ix_conversations_updated_at', 'conversations')
    op.drop_index('ix_conversations_user_id', 'conversations')
    op.drop_table('conversations')
