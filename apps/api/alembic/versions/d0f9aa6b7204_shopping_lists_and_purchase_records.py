"""shopping lists and purchase records

Revision ID: d0f9aa6b7204
Revises: 39e3fa12c259
Create Date: 2026-10-27 21:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd0f9aa6b7204'
down_revision: Union[str, Sequence[str], None] = '39e3fa12c259'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('shopping_lists',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('goal_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['goal_id'], ['goals.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_shopping_lists_user_id'), 'shopping_lists', ['user_id'], unique=False)
    op.create_table('shopping_items',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('list_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('quantity_needed', sa.Integer(), nullable=False),
    sa.Column('estimated_unit_cost_minor', sa.BigInteger(), nullable=True),
    sa.Column('price_source', sa.Enum('estimate', 'verified', name='price_source'), nullable=False),
    sa.Column('seller', sa.String(length=120), nullable=True),
    sa.Column('delivery_cost_minor', sa.BigInteger(), nullable=False),
    sa.Column('transport_cost_minor', sa.BigInteger(), nullable=False),
    sa.Column('fees_minor', sa.BigInteger(), nullable=False),
    sa.Column('status', sa.Enum('needed', 'purchased', name='shopping_item_status'), nullable=False),
    sa.Column('inventory_item_id', sa.Integer(), nullable=True),
    sa.Column('goal_id', sa.Integer(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['goal_id'], ['goals.id'], ),
    sa.ForeignKeyConstraint(['inventory_item_id'], ['inventory_items.id'], ),
    sa.ForeignKeyConstraint(['list_id'], ['shopping_lists.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_shopping_items_list_id'), 'shopping_items', ['list_id'], unique=False)
    op.create_index(op.f('ix_shopping_items_user_id'), 'shopping_items', ['user_id'], unique=False)
    op.create_table('purchase_records',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('shopping_item_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('amount_paid_minor', sa.BigInteger(), nullable=False),
    sa.Column('currency', sa.String(length=8), nullable=False),
    sa.Column('occurred_on', sa.Date(), nullable=False),
    sa.Column('transaction_id', sa.Integer(), nullable=True),
    sa.Column('added_inventory_quantity', sa.Integer(), nullable=False),
    sa.Column('idempotency_key', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['shopping_item_id'], ['shopping_items.id'], ),
    sa.ForeignKeyConstraint(['transaction_id'], ['transactions.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'idempotency_key')
    )
    op.create_index(op.f('ix_purchase_records_shopping_item_id'), 'purchase_records', ['shopping_item_id'], unique=False)
    op.create_index(op.f('ix_purchase_records_user_id'), 'purchase_records', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_purchase_records_user_id'), table_name='purchase_records')
    op.drop_index(op.f('ix_purchase_records_shopping_item_id'), table_name='purchase_records')
    op.drop_table('purchase_records')
    op.drop_index(op.f('ix_shopping_items_user_id'), table_name='shopping_items')
    op.drop_index(op.f('ix_shopping_items_list_id'), table_name='shopping_items')
    op.drop_table('shopping_items')
    op.drop_index(op.f('ix_shopping_lists_user_id'), table_name='shopping_lists')
    op.drop_table('shopping_lists')
