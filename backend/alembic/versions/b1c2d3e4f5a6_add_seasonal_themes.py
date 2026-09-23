"""add seasonal_themes and site_config

Revision ID: b1c2d3e4f5a6
Revises: a1b2c3d4e5f7
Create Date: 2026-09-23

Holiday/locale theming plus the admin-arranged homepage shelf layout.
"""
from alembic import op
import sqlalchemy as sa

revision = "b1c2d3e4f5a6"
down_revision = "a1b2c3d4e5f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "seasonal_themes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("locale", sa.String(length=10), nullable=False, server_default="all"),
        sa.Column("country_code", sa.String(length=2), nullable=True),
        sa.Column("starts_at", sa.DateTime(), nullable=True),
        sa.Column("ends_at", sa.DateTime(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("overrides", sa.Text(), nullable=True),
        sa.Column("shelf_config", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
    )
    op.create_index("ix_seasonal_themes_slug", "seasonal_themes", ["slug"], unique=True)
    op.create_index("ix_seasonal_themes_id", "seasonal_themes", ["id"], unique=False)

    op.create_table(
        "site_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("furniture", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("site_config")
    op.drop_table("seasonal_themes")