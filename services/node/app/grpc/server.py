import grpc
from grpc import aio

from ..config import settings
from .generated import node_pb2_grpc
from .handlers import NodeService


async def start_grpc_server() -> aio.Server:
    server = aio.server()
    node_pb2_grpc.add_NodeServiceServicer_to_server(NodeService(), server)
    server.add_insecure_port(f"{settings.grpc_bind_host}:{settings.grpc_port}")
    await server.start()
    return server
