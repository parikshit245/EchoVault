"""create nodes registry

Revision ID: 0001_create_nodes
Revises:
Create Date: 2026-08-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001_create_nodes"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    node_type = postgresql.ENUM(
        "EVIDENCE", "SECURITY", "MOBILE", "COORDINATOR", name="node_type", create_type=False
    )
    node_status = postgresql.ENUM("ONLINE", "OFFLINE", "UNKNOWN", name="node_status", create_type=False)
    node_type.create(op.get_bind(), checkfirst=True)
    node_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "nodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("node_id", sa.String(length=100), nullable=False),
        sa.Column("node_name", sa.String(length=200), nullable=False),
        sa.Column("node_type", node_type, nullable=False),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("status", node_status, nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("node_id"),
    )
    op.create_index(op.f("ix_nodes_node_id"), "nodes", ["node_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_nodes_node_id"), table_name="nodes")
    op.drop_table("nodes")
    sa.Enum(name="node_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="node_type").drop(op.get_bind(), checkfirst=True)
