"""add_users_table

Revision ID: a1b2c3d4e5f6
Revises: 2727514d7ad8
Create Date: 2026-06-04 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '2727514d7ad8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column('username', sa.String(64), unique=True, nullable=False, index=True),
        sa.Column('email', sa.String(128), unique=True, nullable=False, index=True),
        sa.Column('password_hash', sa.String(256), nullable=False),
        sa.Column('display_name', sa.String(64), server_default=''),
        sa.Column('role', sa.Enum('user', 'admin', name='userrole'), server_default='user', nullable=False),
        sa.Column('status', sa.Enum('active', 'disabled', name='userstatus'), server_default='active', nullable=False),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('users')
    op.execute('DROP TYPE IF EXISTS userrole')
    op.execute('DROP TYPE IF EXISTS userstatus')
