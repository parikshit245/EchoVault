from datetime import datetime, timezone
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models.evidence import Evidence
from ..models.incident import (
    Incident,
    IncidentNode,
    IncidentNodeStatus,
    IncidentRole,
    IncidentSeverity,
    IncidentStatus,
    IncidentType,
)
from ..models.node import Node
from ..schemas.incident import IncidentCreate, IncidentNodeCreate, IncidentUpdate


class IncidentNotFoundError(Exception):
    pass


class IncidentCreatorUnavailableError(Exception):
    pass


class DuplicateIncidentNodeError(Exception):
    pass


class InvalidIncidentTransitionError(Exception):
    pass


ALLOWED_TRANSITIONS: dict[IncidentStatus, set[IncidentStatus]] = {
    IncidentStatus.OPEN: {IncidentStatus.OPEN, IncidentStatus.INVESTIGATING, IncidentStatus.CLOSED},
    IncidentStatus.INVESTIGATING: {IncidentStatus.INVESTIGATING, IncidentStatus.RESOLVED},
    IncidentStatus.RESOLVED: {IncidentStatus.RESOLVED, IncidentStatus.CLOSED},
    IncidentStatus.CLOSED: {IncidentStatus.CLOSED},
}


def new_incident_id() -> str:
    return f"INC-{uuid.uuid4().hex[:12].upper()}"


async def get_incident(session: AsyncSession, incident_id: str) -> Incident | None:
    result = await session.execute(select(Incident).where(Incident.incident_id == incident_id))
    return result.scalar_one_or_none()


async def current_creator(session: AsyncSession) -> Node:
    result = await session.execute(select(Node).where(Node.node_id == settings.node_id))
    node = result.scalar_one_or_none()
    if node is None:
        raise IncidentCreatorUnavailableError(settings.node_id)
    return node


async def create_incident(session: AsyncSession, payload: IncidentCreate) -> Incident:
    creator = await current_creator(session)
    incident = Incident(
        incident_id=new_incident_id(), created_by_node_id=creator.node_id,
        title=payload.title, incident_type=payload.incident_type, description=payload.description,
        severity=payload.severity, location=payload.location, started_at=payload.started_at,
    )
    session.add(incident)
    await session.commit()
    await session.refresh(incident)
    return incident


async def list_incidents(
    session: AsyncSession, *, status: IncidentStatus | None = None,
    incident_type: IncidentType | None = None, severity: IncidentSeverity | None = None,
    created_by_node_id: str | None = None, offset: int = 0, limit: int = 50,
) -> list[Incident]:
    query = select(Incident).order_by(Incident.created_at.desc())
    if status: query = query.where(Incident.status == status)
    if incident_type: query = query.where(Incident.incident_type == incident_type)
    if severity: query = query.where(Incident.severity == severity)
    if created_by_node_id: query = query.where(Incident.created_by_node_id == created_by_node_id)
    result = await session.execute(query.offset(offset).limit(limit))
    return list(result.scalars().unique().all())


async def update_incident(session: AsyncSession, incident: Incident, payload: IncidentUpdate) -> Incident:
    values = payload.model_dump(exclude_unset=True)
    new_status = values.get("status")
    if new_status is not None and new_status not in ALLOWED_TRANSITIONS[incident.status]:
        raise InvalidIncidentTransitionError(f"Cannot transition {incident.status.value} to {new_status.value}")
    for field, value in values.items(): setattr(incident, field, value)
    if new_status in {IncidentStatus.RESOLVED, IncidentStatus.CLOSED} and incident.ended_at is None:
        incident.ended_at = datetime.now(timezone.utc)
    incident.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(incident)
    return incident


async def add_incident_node(session: AsyncSession, incident: Incident, node_id: str, payload: IncidentNodeCreate) -> IncidentNode:
    node_result = await session.execute(select(Node).where(Node.node_id == node_id))
    node = node_result.scalar_one_or_none()
    if node is None: raise IncidentNotFoundError(f"Node '{node_id}' not found")
    existing = await session.get(IncidentNode, (incident.incident_id, node_id))
    if existing is not None: raise DuplicateIncidentNodeError(node_id)
    association = IncidentNode(incident_id=incident.incident_id, node_id=node_id, role=payload.role)
    session.add(association)
    await session.commit()
    await session.refresh(association)
    return association


async def list_incident_nodes(session: AsyncSession, incident_id: str) -> list[IncidentNode]:
    result = await session.execute(select(IncidentNode).where(IncidentNode.incident_id == incident_id).order_by(IncidentNode.joined_at))
    return list(result.scalars().unique().all())


async def remove_incident_node(session: AsyncSession, incident_id: str, node_id: str) -> None:
    association = await session.get(IncidentNode, (incident_id, node_id))
    if association is None: raise IncidentNotFoundError("Association not found")
    association.status = IncidentNodeStatus.INACTIVE
    await session.commit()


async def attach_local_evidence(session: AsyncSession, incident: Incident, evidence_id: str) -> Evidence:
    from .evidence_registry import EvidenceNotFoundError, get_evidence
    evidence = await get_evidence(session, evidence_id)
    evidence.incident_id = incident.incident_id
    evidence.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(evidence)
    return evidence


async def remove_local_evidence(session: AsyncSession, incident: Incident, evidence_id: str) -> Evidence:
    from .evidence_registry import EvidenceNotFoundError, get_evidence
    evidence = await get_evidence(session, evidence_id)
    if evidence.incident_id != incident.incident_id: raise EvidenceNotFoundError(evidence_id)
    evidence.incident_id = None
    evidence.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(evidence)
    return evidence


async def list_local_incident_evidence(session: AsyncSession, incident: Incident) -> list[Evidence]:
    from .evidence_registry import list_evidence
    return await list_evidence(session, incident_id=incident.incident_id)
