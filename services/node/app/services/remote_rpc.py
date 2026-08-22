import json
import uuid

import grpc
from ..config import settings
from ..models.node import Node
from ..grpc.generated import node_pb2, node_pb2_grpc
from ..grpc.time_utils import timestamp_to_datetime
from ..middleware.request_context import request_id_context


class RemoteNodeUnavailableError(Exception):
    pass


class RemoteNotFoundError(Exception):
    pass


async def call_remote(node: Node, method: str, request):
    if not node.grpc_host or not node.grpc_port:
        raise RemoteNodeUnavailableError("Node has no gRPC address")
    request_id = request_id_context.get() or str(uuid.uuid4())
    try:
        async with grpc.aio.insecure_channel(f"{node.grpc_host}:{node.grpc_port}") as channel:
            stub = node_pb2_grpc.NodeServiceStub(channel)
            rpc = getattr(stub, method)
            return await rpc(request, timeout=settings.grpc_timeout_seconds, metadata=(("x-request-id", request_id), ("x-source-node", settings.node_id)))
    except grpc.aio.AioRpcError as exc:
        if exc.code() == grpc.StatusCode.NOT_FOUND:
            raise RemoteNotFoundError(exc.details()) from exc
        raise RemoteNodeUnavailableError(exc.details() or "Remote node unavailable") from exc


def evidence_dict(message):
    return {
        "evidence_id": message.evidence_id, "node_id": message.node_id, "node_name": message.node_name,
        "incident_id": message.incident_id or None, "event_type": message.event_type,
        "evidence_type": message.evidence_type, "title": message.title, "description": message.description or None,
        "captured_at": timestamp_to_datetime(message.captured_at), "received_at": timestamp_to_datetime(message.received_at),
        "location": json.loads(message.location_json) if message.location_json else None,
        "metadata": json.loads(message.metadata_json) if message.metadata_json else None,
        "file_name": message.file_name or None, "mime_type": message.mime_type or None, "file_size": message.file_size or None,
    }


async def remote_status(node: Node):
    return await call_remote(node, "GetNodeStatus", node_pb2.NodeStatusRequest())


async def remote_info(node: Node):
    return await call_remote(node, "GetNodeInfo", node_pb2.NodeInfoRequest())


async def remote_evidence(node: Node, evidence_id: str):
    response = await call_remote(node, "GetEvidence", node_pb2.GetEvidenceRequest(evidence_id=evidence_id))
    return evidence_dict(response.evidence)


async def remote_incident_evidence(node: Node, incident_id: str):
    response = await call_remote(node, "GetEvidenceByIncident", node_pb2.GetEvidenceByIncidentRequest(incident_id=incident_id))
    return [evidence_dict(item) for item in response.evidence]
