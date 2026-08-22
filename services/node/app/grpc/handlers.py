import json
import logging
import time
from datetime import datetime, timezone

import grpc

from ..config import settings
from ..database import async_session_factory
from ..models.node import NodeStatus
from ..services.evidence_registry import EvidenceNotFoundError, get_evidence, list_evidence
from ..services.node_registry import get_node
from .generated import node_pb2, node_pb2_grpc
from .time_utils import datetime_to_timestamp

logger = logging.getLogger("echovault.grpc")


class NodeService(node_pb2_grpc.NodeServiceServicer):
    def _start(self, context, method: str) -> tuple[float, str]:
        metadata = dict(context.invocation_metadata())
        request_id = metadata.get("x-request-id", "grpc-unknown")
        source_node = metadata.get("x-source-node", "unknown")
        return time.perf_counter(), request_id, source_node

    def _log(self, method: str, request_id: str, started: float, status: str) -> None:
        logger.info(json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(), "source_node": request_id, "target_node": settings.node_id, "rpc_method": method, "request_id": request_id, "duration_ms": round((time.perf_counter() - started) * 1000, 2), "status": status}))

    async def _owner(self, context):
        if async_session_factory is None:
            await context.abort(grpc.StatusCode.FAILED_PRECONDITION, "Database is not configured")
        async with async_session_factory() as session:
            node = await get_node(session, settings.node_id)
            if node is None:
                await context.abort(grpc.StatusCode.FAILED_PRECONDITION, "Node is not registered")
            return node

    async def GetNodeInfo(self, request, context):
        started, request_id, source_node = self._start(context, "GetNodeInfo")
        node = await self._owner(context)
        response = node_pb2.NodeInfoResponse(node_id=node.node_id, node_name=node.node_name, node_type=node.node_type.value, host=node.host, port=node.port, status=node.status.value)
        self._log("GetNodeInfo", f"{source_node}:{request_id}", started, "OK")
        return response

    async def GetNodeStatus(self, request, context):
        started, request_id, source_node = self._start(context, "GetNodeStatus")
        node = await self._owner(context)
        response = node_pb2.NodeStatusResponse(node_id=node.node_id, status=node.status.value, timestamp=datetime_to_timestamp(datetime.now(timezone.utc)))
        self._log("GetNodeStatus", f"{source_node}:{request_id}", started, "OK")
        return response

    async def Ping(self, request, context):
        started, request_id, source_node = self._start(context, "Ping")
        node = await self._owner(context)
        response = node_pb2.PingResponse(node_id=node.node_id, status=NodeStatus.ONLINE.value if node.status == NodeStatus.ONLINE else node.status.value, timestamp=datetime_to_timestamp(datetime.now(timezone.utc)))
        self._log("Ping", f"{source_node}:{request_id}", started, "OK")
        return response

    def _evidence_message(self, item):
        message = node_pb2.EvidenceMessage(evidence_id=item.evidence_id, node_id=item.node_id, incident_id=item.incident_id or "", event_type=item.event_type.value, evidence_type=item.evidence_type.value, title=item.title, description=item.description or "", captured_at=datetime_to_timestamp(item.captured_at), received_at=datetime_to_timestamp(item.received_at), location_json=json.dumps(item.location or {}), metadata_json=json.dumps(item.metadata_json or {}), file_name=item.file_name or "", mime_type=item.mime_type or "", file_size=item.file_size or 0, node_name=item.owner.node_name)
        return message

    async def GetEvidence(self, request, context):
        started, request_id, source_node = self._start(context, "GetEvidence")
        if not request.evidence_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "evidence_id is required")
        if async_session_factory is None:
            await context.abort(grpc.StatusCode.FAILED_PRECONDITION, "Database is not configured")
        async with async_session_factory() as session:
            try:
                item = await get_evidence(session, request.evidence_id)
            except EvidenceNotFoundError:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Evidence not found")
        self._log("GetEvidence", f"{source_node}:{request_id}", started, "OK")
        return node_pb2.GetEvidenceResponse(evidence=self._evidence_message(item))

    async def GetEvidenceByIncident(self, request, context):
        started, request_id, source_node = self._start(context, "GetEvidenceByIncident")
        if not request.incident_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "incident_id is required")
        if async_session_factory is None:
            await context.abort(grpc.StatusCode.FAILED_PRECONDITION, "Database is not configured")
        async with async_session_factory() as session:
            items = await list_evidence(session, incident_id=request.incident_id)
        self._log("GetEvidenceByIncident", f"{source_node}:{request_id}", started, "OK")
        return node_pb2.GetEvidenceByIncidentResponse(evidence=[self._evidence_message(item) for item in items])
