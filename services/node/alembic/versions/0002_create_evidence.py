"""create evidence owned by nodes

Revision ID: 0002_create_evidence
Revises: 0001_create_nodes
Create Date: 2026-08-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002_create_evidence"
down_revision: Union[str, None] = "0001_create_nodes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    evidence_type = postgresql.ENUM(
        "IMAGE", "VIDEO", "AUDIO", "TEXT", "SENSOR", "OTHER", name="evidence_type", create_type=False
    )
    event_type = postgresql.ENUM(
        "MOTION_DETECTED", "PERSON_DETECTED", "AUDIO_DETECTED", "DOOR_OPENED",
        "OBJECT_DETECTED", "MANUAL_OBSERVATION", "OTHER", name="event_type", create_type=False
    )
    evidence_type.create(op.get_bind(), checkfirst=True)
    event_type.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_id", sa.String(length=80), nullable=False),
        sa.Column("node_id", sa.String(length=100), nullable=False),
        sa.Column("incident_id", sa.String(length=100), nullable=True),
        sa.Column("evidence_type", evidence_type, nullable=False),
        sa.Column("event_type", event_type, nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("location", postgresql.JSONB(), nullable=True),
        sa.Column("file_name", sa.String(length=255), nullable=True),
        sa.Column("file_path", sa.String(length=500), nullable=True),
        sa.Column("mime_type", sa.String(length=100), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["node_id"], ["nodes.node_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("evidence_id"),
    )
    op.create_index("ix_evidence_evidence_id", "evidence", ["evidence_id"], unique=False)
    op.create_index("ix_evidence_node_id", "evidence", ["node_id"], unique=False)
    op.create_index("ix_evidence_incident_id", "evidence", ["incident_id"], unique=False)
    op.create_index("ix_evidence_captured_at", "evidence", ["captured_at"], unique=False)
    op.create_index("ix_evidence_evidence_type", "evidence", ["evidence_type"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_evidence_evidence_type", table_name="evidence")
    op.drop_index("ix_evidence_captured_at", table_name="evidence")
    op.drop_index("ix_evidence_incident_id", table_name="evidence")
    op.drop_index("ix_evidence_node_id", table_name="evidence")
    op.drop_index("ix_evidence_evidence_id", table_name="evidence")
    op.drop_table("evidence")
    sa.Enum(name="event_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="evidence_type").drop(op.get_bind(), checkfirst=True)