"""
Demo & Fault Simulation REST Router (Part 10).

Provides development & academic evaluation endpoints:
  - POST /api/v1/demo/seed — Idempotently seeds nodes, incident, and multi-node evidence
  - POST /api/v1/demo/simulate/node-status — Toggles node ONLINE/OFFLINE and publishes event
  - POST /api/v1/demo/simulate/event — Injects simulated distributed events into RabbitMQ
  - POST /api/v1/demo/reset — Resets the demonstration environment
"""

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db_session
from ..messaging.publisher import publish_event
from ..messaging.schemas import NodeStatusChangedPayload
from ..models.node import Node, NodeStatus
from ..services.demo_seeder import seed_demo_data

logger = logging.getLogger("echovault.routers.demo")
router = APIRouter(prefix="/api/v1/demo", tags=["Demo & Simulation"])


class NodeStatusSimulationRequest(BaseModel):
    node_id: str
    status: NodeStatus


class SimulateEventRequest(BaseModel):
    event_type: str = Field(min_length=1)
    incident_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


@router.post("/seed", summary="Seed FA-1 demo scenario")
async def seed_demo_endpoint(
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """
    Idempotently seeds 4 distributed nodes, incident INC-000001,
    participating node links, and distributed evidence records.
    """
    try:
        counts = await seed_demo_data(session)
        return {
            "status": "success",
            "message": "EchoVault FA-1 demo environment seeded successfully.",
            "seeded": counts,
        }
    except Exception as exc:
        logger.error("Demo seeding failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Seeding failed: {exc}",
        )


@router.post("/simulate/node-status", summary="Simulate node failure/recovery")
async def simulate_node_status_endpoint(
    body: NodeStatusSimulationRequest,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """
    Simulates a node going OFFLINE or recovering to ONLINE.
    Updates database status and publishes a node.status_changed event to RabbitMQ.
    """
    stmt = select(Node).where(Node.node_id == body.node_id)
    res = await session.execute(stmt)
    node = res.scalar_one_or_none()
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node '{body.node_id}' not found.",
        )

    now = datetime.now(timezone.utc)
    node.status = body.status
    node.updated_at = now
    if body.status == NodeStatus.ONLINE:
        node.last_seen_at = now

    await session.commit()
    await session.refresh(node)

    # Publish to RabbitMQ
    await publish_event(
        event_type="node.status_changed",
        payload=NodeStatusChangedPayload(
            node_id=node.node_id,
            status=node.status.value,
            timestamp=now,
        ).model_dump(mode="json"),
    )

    logger.info("Simulated node %s transition to %s", node.node_id, node.status.value)
    return {
        "status": "success",
        "node_id": node.node_id,
        "new_status": node.status.value,
        "timestamp": now.isoformat(),
    }


@router.post("/simulate/event", summary="Inject custom distributed event")
async def simulate_event_endpoint(body: SimulateEventRequest) -> dict[str, Any]:
    """
    Injects a custom distributed event into RabbitMQ for live dashboard testing.
    """
    await publish_event(
        event_type=body.event_type,
        payload=body.payload,
        incident_id=body.incident_id,
    )
    return {
        "status": "success",
        "event_type": body.event_type,
        "incident_id": body.incident_id,
    }


@router.post("/reset", summary="Reset demonstration environment")
async def reset_demo_endpoint(
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """
    Purges all old leftover test nodes/records and re-seeds only the 4 canonical FA-1 demo nodes.
    """
    from ..services.demo_seeder import clean_reset_demo_data

    counts = await clean_reset_demo_data(session)
    return {
        "status": "success",
        "message": "Database wiped of legacy records and cleanly re-seeded with 4 demo nodes.",
        "seeded": counts,
    }
