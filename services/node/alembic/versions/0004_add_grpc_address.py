"""add gRPC address to nodes

Revision ID: 0004_add_grpc_address
Revises: 0003_create_incidents
Create Date: 2026-08-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_add_grpc_address"
down_revision: Union[str, None] = "0003_create_incidents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("nodes", sa.Column("grpc_host", sa.String(length=255), nullable=True))
    op.add_column("nodes", sa.Column("grpc_port", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("nodes", "grpc_port")
    op.drop_column("nodes", "grpc_host")