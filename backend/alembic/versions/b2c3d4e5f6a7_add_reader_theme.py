"""add reader_theme to users

Revision ID: b2c3d4e5f6a7
Revises: c1d2e3f4a5b6
Create Date: 2026-09-26

The reader used to save its paper colour into the same account column as
the whole-site theme, so picking "Light" inside the reader silently
recoloured the entire storefront (and vice versa) on the next page load.
reader_font_size already had its own column; the reader's theme now gets
one too, so the two settings can be different and sync independently.
"""
from alembic import op
import sqlalchemy as sa

revision = "b2c3d4e5f6a7"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("reader_theme", sa.String(length=5), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "reader_theme")
