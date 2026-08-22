import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.grpc.generated import node_pb2, node_pb2_grpc  # noqa: E402


def test_generated_grpc_contract_is_importable() -> None:
    request = node_pb2.GetEvidenceRequest(evidence_id="EV-test")
    assert request.evidence_id == "EV-test"
    assert hasattr(node_pb2_grpc, "NodeServiceStub")