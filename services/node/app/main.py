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
from .grpc.server import start_grpc_server
from .middleware.request_context import RequestContextMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
	grpc_server = await start_grpc_server()
	try:
		yield
	finally:
		await grpc_server.stop(grace=2)

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
