"""add webrtc support (media capability columns and webrtc_sessions table)

Revision ID: 0007_add_webrtc_support
Revises: 0006_add_p2p_support
Create Date: 2026-08-23

Adds:
  1. supports_video and supports_audio columns to nodes table (Part 9).
  2. webrtc_sessions table for tracking live multimedia sessions with evidence nodes.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_add_webrtc_support"
down_revision: Union[str, None] = "0006_add_p2p_support"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add media capability columns to nodes table
    op.add_column(
        "nodes",
        sa.Column(
            "supports_video",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    op.add_column(
        "nodes",
        sa.Column(
            "supports_audio",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )

    # 2. Create webrtc_sessions table
    op.create_table(
        "webrtc_sessions",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("session_id", sa.String(length=100), nullable=False),
        sa.Column("incident_id", sa.String(length=100), nullable=True),
        sa.Column("requester_id", sa.String(length=100), nullable=False),
        sa.Column("source_node_id", sa.String(length=100), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "REQUESTED",
                "SIGNALING",
                "CONNECTING",
                "CONNECTED",
                "ENDED",
                "FAILED",
                name="webrtc_session_status",
                native_enum=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "has_video",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "has_audio",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", name="uq_webrtc_session_id"),
    )
    op.create_index(
        op.f("ix_webrtc_sessions_session_id"),
        "webrtc_sessions",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_webrtc_sessions_incident_id"),
        "webrtc_sessions",
        ["incident_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_webrtc_sessions_source_node_id"),
        "webrtc_sessions",
        ["source_node_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_webrtc_sessions_status"),
        "webrtc_sessions",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_webrtc_sessions_created_at"),
        "webrtc_sessions",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_webrtc_sessions_created_at"), table_name="webrtc_sessions")
    op.drop_index(op.f("ix_webrtc_sessions_status"), table_name="webrtc_sessions")
    op.drop_index(op.f("ix_webrtc_sessions_source_node_id"), table_name="webrtc_sessions")
    op.drop_index(op.f("ix_webrtc_sessions_incident_id"), table_name="webrtc_sessions")
    op.drop_index(op.f("ix_webrtc_sessions_session_id"), table_name="webrtc_sessions")
    op.drop_table("webrtc_sessions")
    op.execute("DROP TYPE IF EXISTS webrtc_session_status")
    op.drop_column("nodes", "supports_audio")
    op.drop_column("nodes", "supports_video")
