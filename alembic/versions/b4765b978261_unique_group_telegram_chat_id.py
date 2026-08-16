"""unique group telegram_chat_id

Revision ID: b4765b978261
Revises: 20f85fc216c7
Create Date: 2026-08-14 09:12:18.660692

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4765b978261'
down_revision: Union[str, Sequence[str], None] = '20f85fc216c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('groups', schema=None) as batch_op:
        batch_op.create_unique_constraint(batch_op.f('uq_groups_telegram_chat_id'), ['telegram_chat_id'])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('groups', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('uq_groups_telegram_chat_id'), type_='unique')
