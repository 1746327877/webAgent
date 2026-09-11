"""agent server defaults

Revision ID: 94a481626313
Revises: c4637dcce147
Create Date: 2026-09-12 07:05:42.877694

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '94a481626313'
down_revision: str | Sequence[str] | None = 'c4637dcce147'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column("agents", "status", existing_type=sa.String(16), server_default="draft")
    op.alter_column(
        "agents", "model_config", existing_type=postgresql.JSONB(), server_default="{}"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "agents", "model_config", existing_type=postgresql.JSONB(), server_default=None
    )
    op.alter_column("agents", "status", existing_type=sa.String(16), server_default=None)
