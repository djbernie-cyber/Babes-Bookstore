"""add storefront composite indexes for the 90k catalogue

At catalogue scale (~90k rows) the storefront's default query
(WHERE status='approved' AND license_verified=true ORDER BY created_at DESC)
was doing a full scan + sort, costing ~5–6s per page of books. These three
indexes cover the default list and the browse-by filters, keeping page loads
fast as the catalogue grows toward 90,000.

Revision ID: e1f2a3b4c5d6
Revises: d1e2f3a4b5c6
Create Date: 2026-09-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        'ix_books_status_license_created', 'books',
        ['status', 'license_verified', 'created_at'], unique=False,
    )
    op.create_index(
        'ix_books_category_status', 'books',
        ['category', 'status', 'license_verified'], unique=False,
    )
    op.create_index(
        'ix_books_source_status', 'books',
        ['source', 'status', 'license_verified'], unique=False,
    )
    # Description search shares the title/author trigram fast path.
    if op.get_bind().dialect.name == 'postgresql':
        op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')
        op.execute(
            'CREATE INDEX IF NOT EXISTS ix_books_description_trgm '
            'ON books USING gin (description gin_trgm_ops)'
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == 'postgresql':
        op.execute('DROP INDEX IF EXISTS ix_books_description_trgm')
    op.drop_index('ix_books_source_status', table_name='books')
    op.drop_index('ix_books_category_status', table_name='books')
    op.drop_index('ix_books_status_license_created', table_name='books')