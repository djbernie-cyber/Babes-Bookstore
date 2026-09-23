"""add theme_prefs and locale to users

Revision ID: a1b2c3d4e5f7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-23

Personal theme generator output (JSON of CSS variables) plus the locale a
user wants holiday/seasonal theming to come through (e.g. "en-KE").
"""
from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("theme_prefs", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("locale", sa.String(length=10), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "locale")
    op.drop_column("users", "theme_prefs")