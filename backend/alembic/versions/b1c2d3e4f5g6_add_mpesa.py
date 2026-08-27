"""add mpesa fields to purchases

Revision ID: b1c2d3e4f5g6
Revises: afd578650938
Create Date: 2026-08-27
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'b1c2d3e4f5g6'
down_revision: Union[str, None] = 'afd578650938'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('purchases', sa.Column('mpesa_checkout_id', sa.String(length=200), nullable=True))
    op.add_column('purchases', sa.Column('customer_phone', sa.String(length=20), nullable=True))
    op.create_index(op.f('ix_purchases_mpesa_checkout_id'), 'purchases', ['mpesa_checkout_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_purchases_mpesa_checkout_id'), table_name='purchases')
    op.drop_column('purchases', 'customer_phone')
    op.drop_column('purchases', 'mpesa_checkout_id')
