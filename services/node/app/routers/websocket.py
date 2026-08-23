"""
WebSocket endpoint router — Part 7.

Endpoint:
  GET /ws/events   (WebSocket upgrade)

Protocol:
  On connect:
    Server → { type: "connected", connection_id, node_id, timestamp }

  Client commands:
    { type: "ping" }
      → { type: "pong", timestamp }

    { type: "subscribe", filters: { event_types?, source_node_ids?, incident_ids? } }
      → { type: "subscription.updated", filters }

    { type: "unsubscribe", filters: { ... } }
      → { type: "subscription.updated", filters }

    Any other command:
      → { type: "error", code: "UNSUPPORTED_COMMAND", message: "..." }

  Server events (broadcast):
    { type: "event", message_id, event_type, source_node_id, timestamp,
      incident_id, payload, latency_ms }

Design notes:
  - Connection management is fully delegated to ws_manager.
  - Incoming commands are parsed and validated in this router.
  - Broadcasting is handled by EventStreamService — this router only
    handles the inbound control protocol.
  - The receive loop never blocks the event loop — any blocking happens
    inside separate asyncio tasks.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..config import settings
from ..websocket.event_stream import event_stream_service  # noqa: F401 — imported for type ref
from ..websocket.manager import ws_manager
from ..websocket.schemas import (
    ConnectedMessage,
    ErrorMessage,
    PongMessage,
    SubscribeCommand,
    SubscriptionFilters,
    SubscriptionUpdatedMessage,
    UnsubscribeCommand,
)

router = APIRouter(tags=["websocket"])
logger = logging.getLogger("echovault.websocket.router")


@router.websocket("/ws/events")
async def websocket_event_stream(websocket: WebSocket) -> None:
    """
    /ws/events — Continuous real-time EchoVault event stream.

    Accepts WebSocket upgrade, registers client, runs command loop.
    Automatically cleans up on disconnect.
    """
    connection_id = await ws_manager.connect(websocket)

    # Send immediate greeting so the client knows connection_id
    greeting = ConnectedMessage(
        connection_id=connection_id,
        node_id=settings.node_id,
    )
    await ws_manager.send_json(connection_id, greeting.model_dump(mode="json"))

    try:
        while True:
            # Receive next message from client (blocks until a message arrives)
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect:
                break

            ws_manager.touch(connection_id)

            # Parse JSON
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await ws_manager.send_json(
                    connection_id,
                    ErrorMessage(
                        code="INVALID_JSON",
                        message="Message body must be valid JSON",
                    ).model_dump(mode="json"),
                )
                continue

            cmd_type = data.get("type")

            # ── ping ─────────────────────────────────────────────────────────
            if cmd_type == "ping":
                pong = PongMessage()
                await ws_manager.send_json(connection_id, pong.model_dump(mode="json"))

            # ── subscribe ─────────────────────────────────────────────────────
            elif cmd_type == "subscribe":
                try:
                    cmd = SubscribeCommand(**data)
                except Exception:
                    await ws_manager.send_json(
                        connection_id,
                        ErrorMessage(
                            code="INVALID_COMMAND",
                            message="Invalid subscribe command",
                        ).model_dump(mode="json"),
                    )
                    continue
                updated_filters = ws_manager.update_filters(
                    connection_id, cmd.filters, merge=True
                )
                response = SubscriptionUpdatedMessage(filters=updated_filters)
                await ws_manager.send_json(
                    connection_id, response.model_dump(mode="json")
                )
                logger.info(
                    "Client %s subscribed: %s",
                    connection_id,
                    updated_filters.model_dump(),
                )

            # ── unsubscribe ───────────────────────────────────────────────────
            elif cmd_type == "unsubscribe":
                try:
                    cmd = UnsubscribeCommand(**data)
                except Exception:
                    await ws_manager.send_json(
                        connection_id,
                        ErrorMessage(
                            code="INVALID_COMMAND",
                            message="Invalid unsubscribe command",
                        ).model_dump(mode="json"),
                    )
                    continue
                updated_filters = ws_manager.update_filters(
                    connection_id, cmd.filters, merge=False
                )
                response = SubscriptionUpdatedMessage(filters=updated_filters)
                await ws_manager.send_json(
                    connection_id, response.model_dump(mode="json")
                )
                logger.info(
                    "Client %s unsubscribed: %s",
                    connection_id,
                    updated_filters.model_dump(),
                )

            # ── unknown command ───────────────────────────────────────────────
            else:
                await ws_manager.send_json(
                    connection_id,
                    ErrorMessage(
                        code="UNSUPPORTED_COMMAND",
                        message=f"Unsupported WebSocket command: {cmd_type!r}",
                    ).model_dump(mode="json"),
                )
                logger.warning(
                    "Client %s sent unknown command: %s", connection_id, cmd_type
                )

    except WebSocketDisconnect:
        pass  # Normal disconnect — handled in finally
    except Exception as exc:
        logger.exception(
            "Unexpected error in WebSocket handler for %s: %s",
            connection_id,
            exc,
        )
    finally:
        ws_manager.disconnect(connection_id)
