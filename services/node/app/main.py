from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers.health import router as health_router
from .routers.identity import router as identity_router
from .routers.nodes import router as nodes_router
from .routers.evidence import router as evidence_router
from .routers.incidents import router as incidents_router
from .routers.remote import router as remote_router
from .routers.messaging import router as messaging_router
from .grpc.server import start_grpc_server
from .middleware.request_context import RequestContextMiddleware
from .messaging.connection import messaging_connection
from .messaging.consumer import start_consumer, stop_consumer


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

    try:
        yield
    finally:
        # ── Shutdown ──────────────────────────────────────────────────────────
        await grpc_server.stop(grace=2)
        await stop_consumer()
        await messaging_connection.close()


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
