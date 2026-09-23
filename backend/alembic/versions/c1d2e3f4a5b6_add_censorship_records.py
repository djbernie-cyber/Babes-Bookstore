"""add censorship_records

Revision ID: c1d2e3f4a5b6
Revises: b1c2d3e4f5a6
Create Date: 2026-09-23

Why a book is/was banned, by country — powers the Illegal Books Catalog.
"""
from alembic import op
import sqlalchemy as sa

revision = "c1d2e3f4a5b6"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "censorship_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("book_id", sa.Integer(), sa.ForeignKey("books.id", ondelete="CASCADE"), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column("country_name", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="banned"),
        sa.Column("ban_reason", sa.Text(), nullable=False),
        sa.Column("banned_since", sa.String(length=40), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("verified_by", sa.String(length=60), nullable=False, server_default="seed"),
        sa.Column("proposed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
    )
    op.create_index("ix_censorship_records_book_id", "censorship_records", ["book_id"], unique=False)
    op.create_index("ix_censorship_records_id", "censorship_records", ["id"], unique=False)
    op.create_index("ix_censorship_records_status", "censorship_records", ["status"], unique=False)


def downgrade() -> None:
    op.drop_table("censorship_records")