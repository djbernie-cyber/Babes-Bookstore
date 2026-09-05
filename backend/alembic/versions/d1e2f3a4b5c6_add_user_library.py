"""add user library: shelves, shelf_items, reading_progress + user prefs

Revision ID: d1e2f3a4b5c6
Revises: c9d8e7f6a5b4
Create Date: 2026-09-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, None] = 'c9d8e7f6a5b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'shelves',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('is_default', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'name', name='uq_shelf_user_name'),
    )
    op.create_index(op.f('ix_shelves_id'), 'shelves', ['id'], unique=False)
    op.create_index(op.f('ix_shelves_user_id'), 'shelves', ['user_id'], unique=False)
    op.create_index('ix_shelves_user_default', 'shelves', ['user_id', 'is_default'], unique=False)

    op.create_table(
        'shelf_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shelf_id', sa.Integer(), nullable=False),
        sa.Column('book_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['book_id'], ['books.id'], ),
        sa.ForeignKeyConstraint(['shelf_id'], ['shelves.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('shelf_id', 'book_id', name='uq_shelf_item_shelf_book'),
    )
    op.create_index(op.f('ix_shelf_items_id'), 'shelf_items', ['id'], unique=False)
    op.create_index(op.f('ix_shelf_items_shelf_id'), 'shelf_items', ['shelf_id'], unique=False)
    op.create_index(op.f('ix_shelf_items_book_id'), 'shelf_items', ['book_id'], unique=False)

    op.create_table(
        'reading_progress',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('book_id', sa.Integer(), nullable=False),
        sa.Column('percent', sa.Float(), nullable=True),
        sa.Column('position', sa.String(length=500), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['book_id'], ['books.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'book_id', name='uq_reading_user_book'),
    )
    op.create_index(op.f('ix_reading_progress_id'), 'reading_progress', ['id'], unique=False)
    op.create_index(op.f('ix_reading_progress_user_id'), 'reading_progress', ['user_id'], unique=False)
    op.create_index(op.f('ix_reading_progress_book_id'), 'reading_progress', ['book_id'], unique=False)

    op.add_column('users', sa.Column('theme', sa.String(length=20), nullable=True))
    op.add_column('users', sa.Column('reader_font_size', sa.String(length=5), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'reader_font_size')
    op.drop_column('users', 'theme')
    op.drop_index(op.f('ix_reading_progress_book_id'), table_name='reading_progress')
    op.drop_index(op.f('ix_reading_progress_user_id'), table_name='reading_progress')
    op.drop_index(op.f('ix_reading_progress_id'), table_name='reading_progress')
    op.drop_table('reading_progress')
    op.drop_index(op.f('ix_shelf_items_book_id'), table_name='shelf_items')
    op.drop_index(op.f('ix_shelf_items_shelf_id'), table_name='shelf_items')
    op.drop_index(op.f('ix_shelf_items_id'), table_name='shelf_items')
    op.drop_table('shelf_items')
    op.drop_index('ix_shelves_user_default', table_name='shelves')
    op.drop_index(op.f('ix_shelves_user_id'), table_name='shelves')
    op.drop_index(op.f('ix_shelves_id'), table_name='shelves')
    op.drop_table('shelves')
