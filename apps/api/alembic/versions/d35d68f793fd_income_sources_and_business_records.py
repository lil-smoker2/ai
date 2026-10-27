"""income sources and business records

Revision ID: d35d68f793fd
Revises: d0f9aa6b7204
Create Date: 2026-10-27 22:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd35d68f793fd'
down_revision: Union[str, Sequence[str], None] = 'd0f9aa6b7204'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('income_sources',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('expected_amount_minor', sa.BigInteger(), nullable=False),
    sa.Column('frequency', sa.Enum('daily', 'weekly', 'monthly', 'yearly', 'once', name='income_frequency'), nullable=False),
    sa.Column('next_expected_date', sa.Date(), nullable=True),
    sa.Column('reliability', sa.Enum('uncertain', 'likely', 'confirmed', name='income_reliability'), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_income_sources_user_id'), 'income_sources', ['user_id'], unique=False)
    op.create_table('business_records',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('business_name', sa.String(length=120), nullable=False),
    sa.Column('type', sa.Enum('revenue', 'expense', name='business_record_type'), nullable=False),
    sa.Column('amount_minor', sa.BigInteger(), nullable=False),
    sa.Column('category', sa.String(length=80), nullable=True),
    sa.Column('occurred_on', sa.Date(), nullable=False),
    sa.Column('transaction_id', sa.Integer(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['transaction_id'], ['transactions.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_business_records_occurred_on'), 'business_records', ['occurred_on'], unique=False)
    op.create_index(op.f('ix_business_records_user_id'), 'business_records', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_business_records_user_id'), table_name='business_records')
    op.drop_index(op.f('ix_business_records_occurred_on'), table_name='business_records')
    op.drop_table('business_records')
    op.drop_index(op.f('ix_income_sources_user_id'), table_name='income_sources')
    op.drop_table('income_sources')
