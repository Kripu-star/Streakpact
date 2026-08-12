"""add group creator_id

Revision ID: 20f85fc216c7
Revises: 608256f49366
Create Date: 2026-08-11 19:51:14.975773

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20f85fc216c7'
down_revision: Union[str, Sequence[str], None] = '608256f49366'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('groups', schema=None) as batch_op:
        batch_op.add_column(sa.Column('creator_id', sa.String(), nullable=True))
        batch_op.create_foreign_key('fk_groups_creator_id_users', 'users', ['creator_id'], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('groups', schema=None) as batch_op:
        batch_op.drop_constraint('fk_groups_creator_id_users', type_='foreignkey')
        batch_op.drop_column('creator_id')
