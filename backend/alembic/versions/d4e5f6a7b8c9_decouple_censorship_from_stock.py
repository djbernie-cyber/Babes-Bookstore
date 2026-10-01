"""decouple censorship_records from in-stock books

Revision ID: d4e5f6a7b8c9
Revises: b2c3d4e5f6a7
Create Date: 2026-09-27

Why: the archive used to require a carried book (book_id NOT NULL, and the
list query inner-joined approved + asset-verified stock). That made it
structurally impossible to document a ban on any work still in copyright —
i.e. almost the entire postcolonial and African literary canon. The 23-record
result was Western-only by construction, not by editorial choice.

A censorship record is a historical fact about a *work*; carrying an edition
is a licensing decision. They are now separate: book_id may be NULL, and the
work is identified by work_title/work_author/work_year instead.
"""
from alembic import op
import sqlalchemy as sa

revision = "d4e5f6a7b8c9"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "censorship_records",
        "book_id",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.add_column(
        "censorship_records",
        sa.Column("work_title", sa.String(length=240), nullable=True),
    )
    op.add_column(
        "censorship_records",
        sa.Column("work_author", sa.String(length=180), nullable=True),
    )
    op.add_column(
        "censorship_records",
        sa.Column("work_year", sa.String(length=24), nullable=True),
    )
    # Every row must be resolvable to a work one way or the other.
    op.create_check_constraint(
        "ck_censorship_record_has_work",
        "censorship_records",
        "book_id IS NOT NULL OR (work_title IS NOT NULL AND work_title <> '')",
    )
    op.create_index(
        "ix_censorship_records_work_title",
        "censorship_records",
        ["work_title"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_censorship_records_work_title", table_name="censorship_records")
    op.drop_constraint("ck_censorship_record_has_work", "censorship_records", type_="check")
    op.drop_column("censorship_records", "work_year")
    op.drop_column("censorship_records", "work_author")
    op.drop_column("censorship_records", "work_title")
    # Rows created without a carried book cannot survive the old contract.
    op.execute("DELETE FROM censorship_records WHERE book_id IS NULL")
    op.alter_column(
        "censorship_records",
        "book_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
