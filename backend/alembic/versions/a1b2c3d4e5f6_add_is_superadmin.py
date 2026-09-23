"""add is_superadmin to users

Revision ID: a1b2c3d4e5f6
Revises: f2e1d0c9b8a7
Create Date: 2026-09-23

Super-administrators can manage staff/admin accounts, reset passwords and run
the maintenance/repair tooling that keeps the site running.
"""
from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "f2e1d0c9b8a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("is_superadmin", sa.Boolean(), nullable=False, server_default=sa.false()))
    # The site owner account gets super-admin privileges by default.
    op.execute("UPDATE users SET is_superadmin = TRUE, is_admin = TRUE WHERE lower(email) = 'williammajanja@gmail.com'")


def downgrade() -> None:
    op.drop_column("users", "is_superadmin")