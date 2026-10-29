"""scope received message idempotency to the consuming node

Revision ID: 0008_inbox_per_node
Revises: 0007_add_webrtc_support
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_inbox_per_node"
down_revision: Union[str, None] = "0007_add_webrtc_support"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "received_messages",
        sa.Column("consumer_node_id", sa.String(length=100), nullable=True),
    )
    # Existing rows predate the consumer identity. They remain queryable but
    # cannot be safely assigned to a specific process.
    op.execute(
        "UPDATE received_messages SET consumer_node_id = 'legacy' "
        "WHERE consumer_node_id IS NULL"
    )
    op.alter_column("received_messages", "consumer_node_id", nullable=False)
    op.drop_constraint(
        "uq_received_message_id", "received_messages", type_="unique"
    )
    op.create_unique_constraint(
        "uq_received_message_consumer_message",
        "received_messages",
        ["consumer_node_id", "message_id"],
    )
    op.create_index(
        op.f("ix_received_messages_consumer_node_id"),
        "received_messages",
        ["consumer_node_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_received_messages_consumer_node_id"),
        table_name="received_messages",
    )
    op.drop_constraint(
        "uq_received_message_consumer_message", "received_messages", type_="unique"
    )
    op.create_unique_constraint(
        "uq_received_message_id", "received_messages", ["message_id"]
    )
    op.drop_column("received_messages", "consumer_node_id")