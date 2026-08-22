"""add external transcript fields

Revision ID: a7c8d9e0f1a2
Revises: dd7777d4445b
Create Date: 2026-08-22 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a7c8d9e0f1a2"
down_revision: str | None = "dd7777d4445b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("episodes", sa.Column("transcript_provider", sa.String(32), nullable=True))
    op.add_column("episodes", sa.Column("transcript_external_id", sa.String(64), nullable=True))
    op.add_column("episodes", sa.Column("transcript_model", sa.String(64), nullable=True))
    op.add_column("episodes", sa.Column("transcript_language", sa.String(16), nullable=True))


def downgrade() -> None:
    op.drop_column("episodes", "transcript_language")
    op.drop_column("episodes", "transcript_model")
    op.drop_column("episodes", "transcript_external_id")
    op.drop_column("episodes", "transcript_provider")
