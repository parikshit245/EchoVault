from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db_session
from ..models.incident import IncidentSeverity, IncidentStatus, IncidentType
from ..schemas.evidence import EvidenceResponse
from .evidence import as_response as evidence_response
from ..schemas.incident import IncidentCreate, IncidentNodeCreate, IncidentNodeResponse, IncidentResponse, IncidentUpdate
from ..services.evidence_registry import EvidenceNotFoundError
from ..services.incident_registry import (
    DuplicateIncidentNodeError,
    IncidentCreatorUnavailableError,
    IncidentNotFoundError,
    InvalidIncidentTransitionError,
    add_incident_node,
    attach_local_evidence,
    create_incident,
    get_incident,
    list_incident_nodes,
    list_incidents,
    list_local_incident_evidence,
    remove_incident_node,
    remove_local_evidence,
    update_incident,
)

router = APIRouter(prefix="/api/v1/incidents", tags=["incidents"])


def incident_response(incident) -> IncidentResponse:
    return IncidentResponse(
        id=incident.id, incident_id=incident.incident_id, title=incident.title,
        incident_type=incident.incident_type, description=incident.description,
        status=incident.status, severity=incident.severity, location=incident.location,
        started_at=incident.started_at, ended_at=incident.ended_at,
        created_at=incident.created_at, updated_at=incident.updated_at,
        created_by_node_id=incident.created_by_node_id, created_by_node_name=incident.creator.node_name,
    )


def not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Incident not found")


async def require_incident(session: AsyncSession, incident_id: str):
    incident = await get_incident(session, incident_id)
    if incident is None: raise not_found()
    return incident


@router.post("", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED, summary="Create an incident")
async def create_incident_endpoint(payload: IncidentCreate, session: AsyncSession = Depends(get_db_session)) -> IncidentResponse:
    try:
        return incident_response(await create_incident(session, payload))
    except IncidentCreatorUnavailableError as exc:
        raise HTTPException(status_code=409, detail=f"Current node '{exc.args[0]}' is not registered") from exc


@router.get("", response_model=list[IncidentResponse], summary="List incidents")
async def get_incidents(
    incident_status: IncidentStatus | None = Query(default=None, alias="status"),
    incident_type: IncidentType | None = None, severity: IncidentSeverity | None = None,
    created_by_node_id: str | None = None, page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100), session: AsyncSession = Depends(get_db_session),
) -> list[IncidentResponse]:
    records = await list_incidents(session, status=incident_status, incident_type=incident_type, severity=severity,
                                    created_by_node_id=created_by_node_id, offset=(page - 1) * page_size, limit=page_size)
    return [incident_response(item) for item in records]


@router.get("/{incident_id}", response_model=IncidentResponse, summary="Get an incident")
async def get_incident_endpoint(incident_id: str, session: AsyncSession = Depends(get_db_session)) -> IncidentResponse:
    return incident_response(await require_incident(session, incident_id))


@router.patch("/{incident_id}", response_model=IncidentResponse, summary="Update an incident")
async def update_incident_endpoint(incident_id: str, payload: IncidentUpdate, session: AsyncSession = Depends(get_db_session)) -> IncidentResponse:
    incident = await require_incident(session, incident_id)
    try:
        return incident_response(await update_incident(session, incident, payload))
    except InvalidIncidentTransitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{incident_id}/evidence/{evidence_id}", response_model=EvidenceResponse, summary="Attach local evidence")
async def attach_evidence_endpoint(incident_id: str, evidence_id: str, session: AsyncSession = Depends(get_db_session)) -> EvidenceResponse:
    incident = await require_incident(session, incident_id)
    try:
        return evidence_response(await attach_local_evidence(session, incident, evidence_id))
    except EvidenceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Local evidence not found") from exc


@router.delete("/{incident_id}/evidence/{evidence_id}", response_model=EvidenceResponse, summary="Remove local evidence association")
async def remove_evidence_endpoint(incident_id: str, evidence_id: str, session: AsyncSession = Depends(get_db_session)) -> EvidenceResponse:
    incident = await require_incident(session, incident_id)
    try:
        return evidence_response(await remove_local_evidence(session, incident, evidence_id))
    except EvidenceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Local evidence association not found") from exc


@router.get("/{incident_id}/evidence", response_model=list[EvidenceResponse], summary="List local incident evidence")
async def incident_evidence_endpoint(incident_id: str, session: AsyncSession = Depends(get_db_session)) -> list[EvidenceResponse]:
    incident = await require_incident(session, incident_id)
    records = await list_local_incident_evidence(session, incident)
    return [evidence_response(record) for record in records]


@router.post("/{incident_id}/nodes/{node_id}", response_model=IncidentNodeResponse, summary="Add a participating node")
async def add_node_endpoint(incident_id: str, node_id: str, payload: IncidentNodeCreate = IncidentNodeCreate(), session: AsyncSession = Depends(get_db_session)) -> IncidentNodeResponse:
    incident = await require_incident(session, incident_id)
    try:
        association = await add_incident_node(session, incident, node_id, payload)
        await session.refresh(association, ["node"])
        return IncidentNodeResponse(incident_id=association.incident_id, node_id=association.node_id,
                                    node_name=association.node.node_name, role=association.role,
                                    joined_at=association.joined_at, status=association.status)
    except DuplicateIncidentNodeError as exc:
        raise HTTPException(status_code=409, detail=f"Node '{exc.args[0]}' is already associated") from exc
    except IncidentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{incident_id}/nodes", response_model=list[IncidentNodeResponse], summary="List participating nodes")
async def incident_nodes_endpoint(incident_id: str, session: AsyncSession = Depends(get_db_session)) -> list[IncidentNodeResponse]:
    await require_incident(session, incident_id)
    records = await list_incident_nodes(session, incident_id)
    return [IncidentNodeResponse(incident_id=item.incident_id, node_id=item.node_id, node_name=item.node.node_name,
                                 role=item.role, joined_at=item.joined_at, status=item.status) for item in records]


@router.delete("/{incident_id}/nodes/{node_id}", response_model=IncidentNodeResponse, summary="Deactivate a participating node")
async def remove_node_endpoint(incident_id: str, node_id: str, session: AsyncSession = Depends(get_db_session)) -> IncidentNodeResponse:
    await require_incident(session, incident_id)
    try:
        await remove_incident_node(session, incident_id, node_id)
        records = await list_incident_nodes(session, incident_id)
        item = next(record for record in records if record.node_id == node_id)
        return IncidentNodeResponse(incident_id=item.incident_id, node_id=item.node_id, node_name=item.node.node_name,
                                    role=item.role, joined_at=item.joined_at, status=item.status)
    except IncidentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
