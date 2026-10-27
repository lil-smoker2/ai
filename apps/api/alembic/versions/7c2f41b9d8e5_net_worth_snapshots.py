"""net worth snapshots

Revision ID: 7c2f41b9d8e5
Revises: 9ef06de3f2de
Create Date: 2026-10-28 01:15:04.882317

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c2f41b9d8e5'
down_revision: Union[str, Sequence[str], None] = '9ef06de3f2de'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('net_worth_snapshots',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('on_date', sa.Date(), nullable=False),
    sa.Column('net_worth_minor', sa.BigInteger(), nullable=True),
    sa.Column('priced_value_minor', sa.BigInteger(), nullable=False),
    sa.Column('valued_items', sa.Integer(), nullable=False),
    sa.Column('unpriced_items', sa.Integer(), nullable=False),
    sa.Column('complete', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'on_date', name='uq_net_worth_user_date')
    )
    op.create_index(op.f('ix_net_worth_snapshots_user_id'), 'net_worth_snapshots', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_net_worth_snapshots_user_id'), table_name='net_worth_snapshots')
    op.drop_table('net_worth_snapshots')
