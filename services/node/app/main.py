from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import async_session_factory
from .routers.health import router as health_router
from .routers.identity import router as identity_router
from .routers.nodes import router as nodes_router
from .routers.evidence import router as evidence_router
from .routers.incidents import router as incidents_router
from .routers.remote import router as remote_router
from .routers.messaging import router as messaging_router
from .routers.websocket import router as ws_router
from .routers.p2p import router as p2p_router
from .routers.webrtc import router as webrtc_router
from .routers.demo import router as demo_router
from .routers.unit3 import router as unit3_router
from .routers.unit4 import router as unit4_router
from .grpc.server import start_grpc_server
from .middleware.request_context import RequestContextMiddleware
from .messaging.connection import messaging_connection
from .messaging.consumer import start_consumer, stop_consumer
from .p2p.manager import peer_manager
from .webrtc.manager import webrtc_manager
from .models.node import Node, NodeStatus, NodeType

logger = logging.getLogger("echovault.main")


async def _self_register() -> None:
    """
    On startup, upsert this node's own row in the nodes table so that
    host / port always reflect current env-var values.

    This is critical for WebRTC routing: the frontend reads node.host/port
    to determine which URL to send the WebRTC session POST and signaling WS to.
    If host is a Docker-internal service name (e.g. "node-a") the browser
    cannot reach it. NODE_HOST should be set to "localhost" in docker-compose
    so the browser can use the published port mapping.
    """
    if not async_session_factory:
        return
    try:
        from sqlalchemy import select
        from datetime import datetime, timezone

        node_type_map = {
            "evidence": NodeType.EVIDENCE,
            "security": NodeType.SECURITY,
            "mobile": NodeType.MOBILE,
            "coordinator": NodeType.COORDINATOR,
        }
        node_type = node_type_map.get(settings.node_type.lower(), NodeType.COORDINATOR)

        async with async_session_factory() as session:
            result = await session.execute(
                select(Node).where(Node.node_id == settings.node_id)
            )
            node = result.scalar_one_or_none()
            now = datetime.now(timezone.utc)
            if node:
                # Update host/port/status from current env — keep existing name
                node.host = settings.node_host
                node.port = settings.port
                node.status = NodeStatus.ONLINE
                node.last_seen_at = now
                logger.info(
                    "Self-registered: updated %s → host=%s port=%s",
                    settings.node_id, settings.node_host, settings.port,
                )
            else:
                node = Node(
                    node_id=settings.node_id,
                    node_name=settings.app_name,  # Use app_name as node display name
                    node_type=node_type,
                    host=settings.node_host,
                    port=settings.port,
                    grpc_host=settings.grpc_host,
                    grpc_port=settings.grpc_port,
                    p2p_host=settings.p2p_host,
                    p2p_port=settings.p2p_port,
                    supports_video=settings.supports_video,
                    supports_audio=settings.supports_audio,
                    status=NodeStatus.ONLINE,
                    last_seen_at=now,
                )
                session.add(node)
                logger.info(
                    "Self-registered: created %s → host=%s port=%s",
                    settings.node_id, settings.node_host, settings.port,
                )
            await session.commit()
    except Exception as exc:
        logger.warning("Self-registration failed (non-fatal): %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────────
    # 1. Start gRPC server (Part 5)
    grpc_server = await start_grpc_server()

    # 2. Connect RabbitMQ publisher connection (Part 6)
    #    Non-blocking: if RabbitMQ is unavailable the app still starts.
    await messaging_connection.connect()

    # 3. Start RabbitMQ consumer (Part 6)
    #    Declares exchange, node queue, bindings and begins consuming.
    await start_consumer()

    # 4. WebSocket managers (/ws/events for browser stream, /ws/peer for P2P, /ws/webrtc for WebRTC)
    #    are module-level singletons — available automatically on app start.

    # 5. Self-register this node's host/port into the shared DB (Part 7+).
    #    Ensures browser-reachable host:port is always current regardless of seed data.
    await _self_register()

    try:
        yield
    finally:
        # ── Shutdown ──────────────────────────────────────────────────────────
        await grpc_server.stop(grace=2)
        await stop_consumer()
        await messaging_connection.close()
        await peer_manager.close_all()
        await webrtc_manager.close_all()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router)
app.include_router(identity_router)
app.include_router(nodes_router)
app.include_router(evidence_router)
app.include_router(incidents_router)
app.include_router(remote_router)
app.include_router(messaging_router)
app.include_router(ws_router)
app.include_router(p2p_router)
app.include_router(webrtc_router)
app.include_router(demo_router)
app.include_router(unit3_router)
app.include_router(unit4_router)
