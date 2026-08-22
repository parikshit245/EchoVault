from datetime import datetime, timezone
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models.evidence import Evidence, EvidenceType, EventType
from ..models.node import Node
from ..models.incident import Incident
from ..schemas.evidence import EvidenceCreate, EvidenceUpdate
from .file_storage import save_upload


class EvidenceOwnerUnavailableError(Exception):
    pass


class EvidenceNotFoundError(Exception):
    pass


async def current_owner(session: AsyncSession) -> Node:
    result = await session.execute(select(Node).where(Node.node_id == settings.node_id))
    owner = result.scalar_one_or_none()
    if owner is None:
        raise EvidenceOwnerUnavailableError(settings.node_id)
    return owner


def new_evidence_id() -> str:
    return f"EV-{uuid.uuid4().hex[:12].upper()}"


async def create_evidence(
    session: AsyncSession,
    payload: EvidenceCreate,
    *,
    file_name: str | None = None,
    file_path: str | None = None,
    mime_type: str | None = None,
    file_size: int | None = None,
) -> Evidence:
    owner = await current_owner(session)
    if payload.incident_id is not None:
        incident = await session.get(Incident, payload.incident_id)
        if incident is None:
            raise EvidenceNotFoundError(payload.incident_id)
    evidence = Evidence(
        evidence_id=new_evidence_id(),
        node_id=owner.node_id,
        evidence_type=payload.evidence_type,
        event_type=payload.event_type,
        title=payload.title,
        description=payload.description,
        captured_at=payload.captured_at,
        received_at=datetime.now(timezone.utc),
        incident_id=payload.incident_id,
        location=payload.location,
        metadata_json=payload.metadata,
        file_name=file_name,
        file_path=file_path,
        mime_type=mime_type,
        file_size=file_size,
    )
    session.add(evidence)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise RuntimeError("Unable to create evidence") from exc
    await session.refresh(evidence)

    # Publish after successful DB commit — never before
    await _publish_evidence_created(evidence)

    return evidence


async def list_evidence(
    session: AsyncSession,
    *,
    evidence_type: EvidenceType | None = None,
    incident_id: str | None = None,
    from_timestamp: datetime | None = None,
    to_timestamp: datetime | None = None,
    offset: int = 0,
    limit: int = 50,
) -> list[Evidence]:
    owner = await current_owner(session)
    query = select(Evidence).where(Evidence.node_id == owner.node_id, Evidence.deleted_at.is_(None))
    if evidence_type:
        query = query.where(Evidence.evidence_type == evidence_type)
    if incident_id:
        query = query.where(Evidence.incident_id == incident_id)
    if from_timestamp:
        query = query.where(Evidence.captured_at >= from_timestamp)
    if to_timestamp:
        query = query.where(Evidence.captured_at <= to_timestamp)
    result = await session.execute(query.order_by(Evidence.captured_at.desc()).offset(offset).limit(limit))
    return list(result.scalars().unique().all())


async def get_evidence(session: AsyncSession, evidence_id: str) -> Evidence:
    owner = await current_owner(session)
    result = await session.execute(
        select(Evidence).where(
            Evidence.evidence_id == evidence_id,
            Evidence.node_id == owner.node_id,
            Evidence.deleted_at.is_(None),
        )
    )
    evidence = result.scalar_one_or_none()
    if evidence is None:
        raise EvidenceNotFoundError(evidence_id)
    return evidence


async def update_evidence(session: AsyncSession, evidence: Evidence, payload: EvidenceUpdate) -> Evidence:
    values = payload.model_dump(exclude_unset=True)
    if values.get("incident_id") is not None:
        incident = await session.get(Incident, values["incident_id"])
        if incident is None:
            raise EvidenceNotFoundError(values["incident_id"])
    if "metadata" in values:
        evidence.metadata_json = values.pop("metadata")
    for field, value in values.items():
        setattr(evidence, field, value)
    evidence.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(evidence)

    # Publish after successful DB commit
    await _publish_evidence_updated(evidence)

    return evidence


async def delete_evidence(session: AsyncSession, evidence: Evidence) -> Evidence:
    evidence.deleted_at = datetime.now(timezone.utc)
    evidence.updated_at = evidence.deleted_at
    await session.commit()
    await session.refresh(evidence)

    # Publish after successful DB commit
    await _publish_evidence_deleted(evidence)

    return evidence


async def create_uploaded_evidence(
    session: AsyncSession,
    payload: EvidenceCreate,
    upload,
) -> Evidence:
    owner = await current_owner(session)
    if payload.incident_id is not None:
        incident = await session.get(Incident, payload.incident_id)
        if incident is None:
            raise EvidenceNotFoundError(payload.incident_id)
    evidence_id = new_evidence_id()
    storage_key, file_size = await save_upload(upload, owner.node_id, evidence_id)
    try:
        evidence = Evidence(
            evidence_id=evidence_id,
            node_id=owner.node_id,
            evidence_type=payload.evidence_type,
            event_type=payload.event_type,
            title=payload.title,
            description=payload.description,
            captured_at=payload.captured_at,
            received_at=datetime.now(timezone.utc),
            incident_id=payload.incident_id,
            location=payload.location,
            metadata_json=payload.metadata,
            file_name=upload.filename,
            file_path=storage_key,
            mime_type=upload.content_type,
            file_size=file_size,
        )
        session.add(evidence)
        await session.commit()
        await session.refresh(evidence)

        # Publish after successful DB commit — file already saved
        await _publish_evidence_created(evidence)

        return evidence
    except Exception:
        await session.rollback()
        from .file_storage import resolve_storage_key
        resolve_storage_key(storage_key).unlink(missing_ok=True)
        raise


# ── Private publish helpers ───────────────────────────────────────────────────

async def _publish_evidence_created(evidence: Evidence) -> None:
    try:
        from ..messaging.publisher import publish_event
        from ..messaging.schemas import EvidenceCreatedPayload
        await publish_event(
            "evidence.created",
            EvidenceCreatedPayload(
                evidence_id=evidence.evidence_id,
                node_id=evidence.node_id,
                event_type=evidence.event_type.value,
                evidence_type=evidence.evidence_type.value,
                title=evidence.title,
                incident_id=evidence.incident_id,
                captured_at=evidence.captured_at,
            ),
            incident_id=evidence.incident_id,
        )
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger("echovault.services.evidence").warning(
            "Could not publish evidence.created: %s", exc
        )


async def _publish_evidence_updated(evidence: Evidence) -> None:
    try:
        from ..messaging.publisher import publish_event
        from ..messaging.schemas import EvidenceUpdatedPayload
        await publish_event(
            "evidence.updated",
            EvidenceUpdatedPayload(
                evidence_id=evidence.evidence_id,
                node_id=evidence.node_id,
                incident_id=evidence.incident_id,
                title=evidence.title,
                description=evidence.description,
                updated_at=evidence.updated_at,
            ),
            incident_id=evidence.incident_id,
        )
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger("echovault.services.evidence").warning(
            "Could not publish evidence.updated: %s", exc
        )


async def _publish_evidence_deleted(evidence: Evidence) -> None:
    try:
        from ..messaging.publisher import publish_event
        from ..messaging.schemas import EvidenceDeletedPayload
        await publish_event(
            "evidence.deleted",
            EvidenceDeletedPayload(
                evidence_id=evidence.evidence_id,
                node_id=evidence.node_id,
                incident_id=evidence.incident_id,
                deleted_at=evidence.deleted_at,
            ),
            incident_id=evidence.incident_id,
        )
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger("echovault.services.evidence").warning(
            "Could not publish evidence.deleted: %s", exc
        )
