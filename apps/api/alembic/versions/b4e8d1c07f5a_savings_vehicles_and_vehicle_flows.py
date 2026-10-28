"""Savings vehicles and their flow records.

The places money can sit (M-PESA savings products, banks, SACCOs, holdings,
betting sites) plus what the person says went in and came back out. Money is
integer minor units; rate_percent is a percentage per year as it was quoted, and
every rate or valuation stands with the date it was checked, because this app is
offline and cannot know a platform's current terms.

Revision ID: b4e8d1c07f5a
Revises: a1c7f3d94b62
Create Date: 2026-10-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b4e8d1c07f5a'
down_revision: Union[str, Sequence[str], None] = 'a1c7f3d94b62'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'savings_vehicles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column(
            'kind',
            sa.Enum('mpesa', 'bank', 'sacco', 'money_market', 'shares',
                    'betting', 'other', name='vehicle_kind'),
            nullable=False,
        ),
        sa.Column('url', sa.String(length=300), nullable=True),
        # A percentage, not money: 10.75 means 10.75% a year, exactly as quoted.
        sa.Column('rate_percent', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('rate_checked_on', sa.Date(), nullable=True),
        sa.Column('units', sa.Numeric(precision=12, scale=4), nullable=True),
        # Nullable on purpose: a value nobody entered has never been recorded,
        # which is not the same as a holding worth nothing.
        sa.Column('value_minor', sa.BigInteger(), nullable=True),
        sa.Column('valued_on', sa.Date(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_savings_vehicles_user_id'), 'savings_vehicles',
                    ['user_id'], unique=False)

    op.create_table(
        'vehicle_flows',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('vehicle_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column(
            'direction',
            sa.Enum('in', 'out', name='vehicle_flow_direction'),
            nullable=False,
        ),
        sa.Column('amount_minor', sa.BigInteger(), nullable=False),
        sa.Column('occurred_on', sa.Date(), nullable=False),
        sa.Column('note', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['vehicle_id'], ['savings_vehicles.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_vehicle_flows_vehicle_id'), 'vehicle_flows',
                    ['vehicle_id'], unique=False)
    op.create_index(op.f('ix_vehicle_flows_user_id'), 'vehicle_flows',
                    ['user_id'], unique=False)
    op.create_index(op.f('ix_vehicle_flows_occurred_on'), 'vehicle_flows',
                    ['occurred_on'], unique=False)


def downgrade() -> None:
    # Both tables are dropped rather than left holding orphan rows: a note about
    # money staked or saved is worthless without the place it refers to.
    op.drop_index(op.f('ix_vehicle_flows_occurred_on'), table_name='vehicle_flows')
    op.drop_index(op.f('ix_vehicle_flows_user_id'), table_name='vehicle_flows')
    op.drop_index(op.f('ix_vehicle_flows_vehicle_id'), table_name='vehicle_flows')
    op.drop_table('vehicle_flows')
    op.drop_index(op.f('ix_savings_vehicles_user_id'), table_name='savings_vehicles')
    op.drop_table('savings_vehicles')
