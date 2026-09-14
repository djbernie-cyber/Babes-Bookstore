"""add refunds (M-Pesa B2Pochi payouts)

Revision ID: f2e1d0c9b8a7
Revises: e1f2a3b4c5d6
Create Date: 2026-09-14
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'f2e1d0c9b8a7'
down_revision: Union[str, None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'refunds',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('purchase_id', sa.Integer(), sa.ForeignKey('purchases.id'), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(length=10), server_default='kes'),
        sa.Column('originator_conversation_id', sa.String(length=100), nullable=True),
        sa.Column('conversation_id', sa.String(length=100), nullable=True),
        sa.Column('transaction_id', sa.String(length=100), nullable=True),
        sa.Column('customer_phone', sa.String(length=20), nullable=True),
        sa.Column('status', sa.String(length=20), server_default='pending'),
        sa.Column('result_code', sa.String(length=20), nullable=True),
        sa.Column('result_desc', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(op.f('ix_refunds_id'), 'refunds', ['id'])
    op.create_index(op.f('ix_refunds_purchase_id'), 'refunds', ['purchase_id'])
    op.create_index(op.f('ix_refunds_status'), 'refunds', ['status'])
    op.create_index(op.f('ix_refunds_originator_conversation_id'), 'refunds', ['originator_conversation_id'], unique=True)
    op.create_index(op.f('ix_refunds_conversation_id'), 'refunds', ['conversation_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_refunds_conversation_id'), table_name='refunds')
    op.drop_index(op.f('ix_refunds_originator_conversation_id'), table_name='refunds')
    op.drop_index(op.f('ix_refunds_status'), table_name='refunds')
    op.drop_index(op.f('ix_refunds_purchase_id'), table_name='refunds')
    op.drop_index(op.f('ix_refunds_id'), table_name='refunds')
    op.drop_table('refunds')