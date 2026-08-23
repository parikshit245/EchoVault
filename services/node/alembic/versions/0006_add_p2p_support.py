"""add p2p support (nodes columns and peer_messages table)

Revision ID: 0006_add_p2p_support
Revises: 0005_create_received_messages
Create Date: 2026-08-23

Adds:
  1. p2p_host and p2p_port columns to nodes table for P2P endpoint discovery (Part 8).
  2. peer_messages table for local P2P inbox, auditing, and idempotency tracking.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_add_p2p_support"
down_revision: Union[str, None] = "0005_create_received_messages"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add p2p address fields to nodes table
    op.add_column("nodes", sa.Column("p2p_host", sa.String(length=255), nullable=True))
    op.add_column("nodes", sa.Column("p2p_port", sa.Integer(), nullable=True))

    # 2. Create peer_messages table
    op.create_table(
        "peer_messages",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("message_id", sa.String(length=100), nullable=False),
        sa.Column("source_node_id", sa.String(length=100), nullable=False),
        sa.Column("target_node_id", sa.String(length=100), nullable=False),
        sa.Column("message_type", sa.String(length=100), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "RECEIVED",
                "PROCESSED",
                "FAILED",
                "IGNORED",
                name="peer_message_status",
                native_enum=True,
            ),
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", name="uq_peer_message_id"),
    )
    op.create_index(
        op.f("ix_peer_messages_message_id"),
        "peer_messages",
        ["message_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_peer_messages_source_node_id"),
        "peer_messages",
        ["source_node_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_peer_messages_target_node_id"),
        "peer_messages",
        ["target_node_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_peer_messages_message_type"),
        "peer_messages",
        ["message_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_peer_messages_received_at"),
        "peer_messages",
        ["received_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_peer_messages_status"),
        "peer_messages",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_peer_messages_status"), table_name="peer_messages")
    op.drop_index(op.f("ix_peer_messages_received_at"), table_name="peer_messages")
    op.drop_index(op.f("ix_peer_messages_message_type"), table_name="peer_messages")
    op.drop_index(op.f("ix_peer_messages_target_node_id"), table_name="peer_messages")
    op.drop_index(op.f("ix_peer_messages_source_node_id"), table_name="peer_messages")
    op.drop_index(op.f("ix_peer_messages_message_id"), table_name="peer_messages")
    op.drop_table("peer_messages")
    op.execute("DROP TYPE IF EXISTS peer_message_status")
    op.drop_column("nodes", "p2p_port")
    op.drop_column("nodes", "p2p_host")
