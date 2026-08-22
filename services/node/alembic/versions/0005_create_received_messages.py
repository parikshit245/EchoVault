"""create received_messages table

Revision ID: 0005_create_received_messages
Revises: 0004_add_grpc_address
Create Date: 2026-08-22

Adds the local message inbox for RabbitMQ-consumed events (Part 6).
The unique constraint on message_id enforces idempotency —
duplicate deliveries are detected without processing the message twice.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_create_received_messages"
down_revision: Union[str, None] = "0004_add_grpc_address"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "received_messages",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("message_id", sa.String(length=100), nullable=False),
        sa.Column("source_node_id", sa.String(length=100), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("routing_key", sa.String(length=200), nullable=False),
        sa.Column("incident_id", sa.String(length=100), nullable=True),
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
                name="received_message_status",
                native_enum=True,
            ),
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", name="uq_received_message_id"),
    )
    op.create_index(
        op.f("ix_received_messages_event_type"),
        "received_messages",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_received_messages_incident_id"),
        "received_messages",
        ["incident_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_received_messages_message_id"),
        "received_messages",
        ["message_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_received_messages_received_at"),
        "received_messages",
        ["received_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_received_messages_source_node_id"),
        "received_messages",
        ["source_node_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_received_messages_status"),
        "received_messages",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_received_messages_status"), table_name="received_messages")
    op.drop_index(op.f("ix_received_messages_source_node_id"), table_name="received_messages")
    op.drop_index(op.f("ix_received_messages_received_at"), table_name="received_messages")
    op.drop_index(op.f("ix_received_messages_message_id"), table_name="received_messages")
    op.drop_index(op.f("ix_received_messages_incident_id"), table_name="received_messages")
    op.drop_index(op.f("ix_received_messages_event_type"), table_name="received_messages")
    op.drop_table("received_messages")
    op.execute("DROP TYPE IF EXISTS received_message_status")
