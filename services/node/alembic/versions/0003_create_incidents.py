"""create incidents and incident nodes

Revision ID: 0003_create_incidents
Revises: 0002_create_evidence
Create Date: 2026-08-22
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003_create_incidents"
down_revision: Union[str, None] = "0002_create_evidence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    enums = [
        postgresql.ENUM("SECURITY", "ACCIDENT", "INTRUSION", "THEFT", "VANDALISM", "INFRASTRUCTURE", "OTHER", name="incident_type", create_type=True),
        postgresql.ENUM("OPEN", "INVESTIGATING", "RESOLVED", "CLOSED", name="incident_status", create_type=True),
        postgresql.ENUM("LOW", "MEDIUM", "HIGH", "CRITICAL", name="incident_severity", create_type=True),
        postgresql.ENUM("OBSERVER", "INVESTIGATOR", "COORDINATOR", name="incident_role", create_type=True),
        postgresql.ENUM("ACTIVE", "INACTIVE", name="incident_node_status", create_type=True),
    ]
    for item in enums: item.create(bind, checkfirst=True)
    for item in enums: item.create_type = False
    op.create_table(
        "incidents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", sa.String(100), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("incident_type", enums[0], nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", enums[1], nullable=False, server_default="OPEN"),
        sa.Column("severity", enums[2], nullable=False, server_default="MEDIUM"),
        sa.Column("location", postgresql.JSONB(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by_node_id", sa.String(100), nullable=False),
        sa.ForeignKeyConstraint(["created_by_node_id"], ["nodes.node_id"]),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("incident_id"),
    )
    for name, column in [("incident_id", "incident_id"), ("incident_status", "status"), ("incident_type", "incident_type"), ("incident_severity", "severity"), ("incident_created_at", "created_at"), ("incident_created_by_node", "created_by_node_id")]:
        op.create_index(f"ix_{name}", "incidents", [column], unique=False)
    op.create_table(
        "incident_nodes",
        sa.Column("incident_id", sa.String(100), nullable=False),
        sa.Column("node_id", sa.String(100), nullable=False),
        sa.Column("role", enums[3], nullable=False, server_default="OBSERVER"),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("status", enums[4], nullable=False, server_default="ACTIVE"),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.incident_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["node_id"], ["nodes.node_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("incident_id", "node_id"),
    )
    op.create_foreign_key("fk_evidence_incident", "evidence", "incidents", ["incident_id"], ["incident_id"])


def downgrade() -> None:
    op.drop_constraint("fk_evidence_incident", "evidence", type_="foreignkey")
    op.drop_table("incident_nodes")
    for name in ["incident_created_by_node", "incident_created_at", "incident_severity", "incident_type", "incident_status", "incident_id"]:
        op.drop_index(f"ix_{name}", table_name="incidents")
    op.drop_table("incidents")
    for name in ["incident_node_status", "incident_role", "incident_severity", "incident_status", "incident_type"]:
        sa.Enum(name=name).drop(op.get_bind(), checkfirst=True)
