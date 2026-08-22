"""
Messaging API router — Part 6.

Routes:
  GET  /api/v1/messaging/messages   — paginated received-message history (local node only)
  POST /api/v1/messaging/test       — ⚠ DEV/TESTING ONLY — publish a test message

The /messaging/messages endpoint returns only this node's local inbox.
There is no global centralized message history — each node owns its own records.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db_session
from ..messaging.connection import messaging_connection
from ..messaging.publisher import publish_event
from ..messaging.schemas import DevTestPayload
from ..models.received_message import ReceivedMessage, ReceivedMessageStatus
from ..schemas.messaging import ReceivedMessageResponse

router = APIRouter(prefix="/api/v1/messaging", tags=["messaging"])
logger = logging.getLogger("echovault.routers.messaging")


@router.get(
    "/messages",
    response_model=list[ReceivedMessageResponse],
    summary="List received messages (local node inbox)",
)
async def list_received_messages(
    event_type: str | None = Query(default=None, description="Filter by event type"),
    source_node_id: str | None = Query(default=None, description="Filter by source node"),
    msg_status: ReceivedMessageStatus | None = Query(
        default=None, alias="status", description="Filter by processing status"
    ),
    incident_id: str | None = Query(default=None, description="Filter by incident ID"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_db_session),
) -> list[ReceivedMessageResponse]:
    """
    Return this node's local received-message history.

    Supports filtering by event_type, source_node_id, status, and incident_id.
    Results are ordered by received_at descending (newest first).
    """
    query = (
        select(ReceivedMessage)
        .order_by(ReceivedMessage.received_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    if event_type:
        query = query.where(ReceivedMessage.event_type == event_type)
    if source_node_id:
        query = query.where(ReceivedMessage.source_node_id == source_node_id)
    if msg_status:
        query = query.where(ReceivedMessage.status == msg_status)
    if incident_id:
        query = query.where(ReceivedMessage.incident_id == incident_id)

    result = await session.execute(query)
    records = result.scalars().all()
    return [ReceivedMessageResponse.model_validate(r) for r in records]


@router.post(
    "/test",
    status_code=status.HTTP_202_ACCEPTED,
    summary="[DEV ONLY] Publish a test message",
    description=(
        "**Development and testing endpoint only.** "
        "Publishes a test.message event through RabbitMQ. "
        "This is NOT part of the EchoVault business workflow."
    ),
)
async def publish_test_message(
    body: dict[str, Any],
) -> dict[str, str]:
    """
    ⚠ DEV/TESTING ONLY — not used in the production EchoVault workflow.

    Publish a raw test message through the RabbitMQ exchange so you can
    observe message routing in the RabbitMQ management UI.

    Example body:
        {"event_type": "test.message", "payload": {"message": "Hello from CCTV-A"}}
    """
    if not messaging_connection.is_healthy():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RabbitMQ is not available",
        )

    event_type = body.get("event_type", "test.message")
    payload_data = body.get("payload", {})

    try:
        test_payload = DevTestPayload(
            message=str(payload_data.get("message", "test")),
            extra={k: v for k, v in payload_data.items() if k != "message"},
        )
        await publish_event(event_type, test_payload)
        logger.info("[DEV] Test message published: event_type=%s", event_type)
        return {"status": "published", "event_type": event_type}
    except Exception as exc:
        logger.error("Failed to publish test message: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to publish: {exc}",
        ) from exc
