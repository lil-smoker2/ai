"""account details: M-PESA number, bank name, account number, M-Shwari type

Revision ID: a1c7f3d94b62
Revises: 7c2f41b9d8e5
Create Date: 2026-10-28 09:12:44.118372

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1c7f3d94b62'
down_revision: Union[str, Sequence[str], None] = '7c2f41b9d8e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_TYPES = ('cash', 'mpesa', 'bank', 'wallet', 'custom')
NEW_TYPES = ('cash', 'mpesa', 'mshwari', 'bank', 'wallet', 'custom')


def upgrade() -> None:
    """Upgrade schema."""
    # Nullable, and no default: an account whose number was never typed stays
    # unknown rather than being filled with an empty string or a fake figure.
    op.add_column('accounts', sa.Column('mpesa_number', sa.String(length=20), nullable=True))
    op.add_column('accounts', sa.Column('bank_name', sa.String(length=80), nullable=True))
    op.add_column('accounts', sa.Column('account_number', sa.String(length=30), nullable=True))

    # SQLite renders an Enum as VARCHAR sized from the longest value ('custom'
    # was 6), with no CHECK constraint. The length is not enforced, so existing
    # rows keep working either way - this step only brings an upgraded database
    # to the same shape a fresh one gets, so the two do not drift apart.
    with op.batch_alter_table('accounts') as batch_op:
        batch_op.alter_column(
            'type',
            existing_type=sa.Enum(*OLD_TYPES, name='account_type'),
            type_=sa.Enum(*NEW_TYPES, name='account_type'),
            existing_nullable=False,
        )


def downgrade() -> None:
    """Downgrade schema.

    Rows already recorded as an M-Shwari account do not fit the older value
    list; they are folded back to 'wallet' so a downgrade cannot destroy them.
    """
    op.execute("UPDATE accounts SET type = 'wallet' WHERE type = 'mshwari'")
    with op.batch_alter_table('accounts') as batch_op:
        batch_op.alter_column(
            'type',
            existing_type=sa.Enum(*NEW_TYPES, name='account_type'),
            type_=sa.Enum(*OLD_TYPES, name='account_type'),
            existing_nullable=False,
        )
        batch_op.drop_column('account_number')
        batch_op.drop_column('bank_name')
        batch_op.drop_column('mpesa_number')
