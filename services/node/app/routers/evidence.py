import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db_session
from ..models.evidence import EvidenceType, EventType
from ..schemas.evidence import EvidenceCreate, EvidenceResponse, EvidenceUpdate
from ..services.evidence_registry import (
    EvidenceNotFoundError,
    EvidenceOwnerUnavailableError,
    create_evidence,
    create_uploaded_evidence,
    delete_evidence,
    get_evidence,
    list_evidence,
    update_evidence,
)
from ..services.file_storage import InvalidUploadError, resolve_storage_key

router = APIRouter(prefix="/api/v1/evidence", tags=["evidence"])


def as_response(evidence) -> EvidenceResponse:
    owner_name = evidence.owner.node_name if getattr(evidence, "owner", None) else evidence.node_id
    return EvidenceResponse(
        id=evidence.id,
        evidence_id=evidence.evidence_id,
        node_id=evidence.node_id,
        node_name=owner_name,
        incident_id=evidence.incident_id,
        evidence_type=evidence.evidence_type,
        event_type=evidence.event_type,
        title=evidence.title,
        description=evidence.description,
        captured_at=evidence.captured_at,
        received_at=evidence.received_at,
        location=evidence.location,
        file_name=evidence.file_name,
        file_path=evidence.file_path,
        mime_type=evidence.mime_type,
        file_size=evidence.file_size,
        metadata=evidence.metadata_json,
        deleted_at=evidence.deleted_at,
        created_at=evidence.created_at,
        updated_at=evidence.updated_at,
    )


def owner_error(exc: EvidenceOwnerUnavailableError) -> HTTPException:
    return HTTPException(status_code=409, detail=f"Current node '{exc.args[0]}' is not registered")


@router.post("", response_model=EvidenceResponse, status_code=status.HTTP_201_CREATED, summary="Create local evidence")
async def create_local_evidence(
    payload: EvidenceCreate,
    session: AsyncSession = Depends(get_db_session),
) -> EvidenceResponse:
    try:
        return as_response(await create_evidence(session, payload))
    except EvidenceOwnerUnavailableError as exc:
        raise owner_error(exc) from exc
    except EvidenceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Incident not found") from exc


@router.get("", response_model=list[EvidenceResponse], summary="List evidence owned by this node")
async def get_local_evidence(
    evidence_type: EvidenceType | None = Query(default=None),
    incident_id: str | None = Query(default=None),
    from_timestamp: datetime | None = Query(default=None),
    to_timestamp: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
) -> list[EvidenceResponse]:
    try:
        records = await list_evidence(
            session,
            evidence_type=evidence_type,
            incident_id=incident_id,
            from_timestamp=from_timestamp,
            to_timestamp=to_timestamp,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        return [as_response(record) for record in records]
    except EvidenceOwnerUnavailableError as exc:
        raise owner_error(exc) from exc


@router.post("/upload", response_model=EvidenceResponse, status_code=status.HTTP_201_CREATED, summary="Upload local evidence")
async def upload_local_evidence(
    file: UploadFile = File(...),
    evidence_type: EvidenceType = Form(...),
    event_type: EventType = Form(EventType.OTHER),
    title: str = Form(...),
    description: str | None = Form(None),
    captured_at: datetime | None = Form(None),
    incident_id: str | None = Form(None),
    location: str | None = Form(None),
    metadata: str | None = Form(None),
    session: AsyncSession = Depends(get_db_session),
) -> EvidenceResponse:
    try:
        parsed_location = json.loads(location) if location else None
        parsed_metadata = json.loads(metadata) if metadata else None
        payload = EvidenceCreate(
            evidence_type=evidence_type,
            event_type=event_type,
            title=title,
            description=description,
            captured_at=captured_at or datetime.now(timezone.utc),
            incident_id=incident_id,
            location=parsed_location,
            metadata=parsed_metadata,
        )
        return as_response(await create_uploaded_evidence(session, payload, file))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="location and metadata must be valid JSON") from exc
    except InvalidUploadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except EvidenceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Incident not found") from exc
    except EvidenceOwnerUnavailableError as exc:
        raise owner_error(exc) from exc


@router.get("/{evidence_id}", response_model=EvidenceResponse, summary="Get local evidence")
async def get_local_evidence_item(
    evidence_id: str, session: AsyncSession = Depends(get_db_session)
) -> EvidenceResponse:
    try:
        return as_response(await get_evidence(session, evidence_id))
    except EvidenceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Evidence not found") from exc
    except EvidenceOwnerUnavailableError as exc:
        raise owner_error(exc) from exc


@router.patch("/{evidence_id}", response_model=EvidenceResponse, summary="Update local evidence metadata")
async def update_local_evidence(
    evidence_id: str,
    payload: EvidenceUpdate,
    session: AsyncSession = Depends(get_db_session),
) -> EvidenceResponse:
    try:
        evidence = await get_evidence(session, evidence_id)
        return as_response(await update_evidence(session, evidence, payload))
    except EvidenceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Evidence not found") from exc
    except EvidenceOwnerUnavailableError as exc:
        raise owner_error(exc) from exc


@router.delete("/{evidence_id}", response_model=EvidenceResponse, summary="Soft-delete local evidence")
async def delete_local_evidence(
    evidence_id: str, session: AsyncSession = Depends(get_db_session)
) -> EvidenceResponse:
    try:
        evidence = await get_evidence(session, evidence_id)
        return as_response(await delete_evidence(session, evidence))
    except EvidenceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Evidence not found") from exc
    except EvidenceOwnerUnavailableError as exc:
        raise owner_error(exc) from exc


@router.get("/{evidence_id}/file", summary="Download a local evidence file")
async def download_evidence_file(
    evidence_id: str, session: AsyncSession = Depends(get_db_session)
) -> FileResponse:
    try:
        evidence = await get_evidence(session, evidence_id)
    except EvidenceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Evidence file not found") from exc
    except EvidenceOwnerUnavailableError as exc:
        raise owner_error(exc) from exc
    if not evidence.file_path:
        raise HTTPException(status_code=404, detail="Evidence has no file")
    try:
        path = resolve_storage_key(evidence.file_path)
    except InvalidUploadError as exc:
        raise HTTPException(status_code=404, detail="Evidence file not found") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Evidence file not found")
    return FileResponse(path, media_type=evidence.mime_type, filename=evidence.file_name)
