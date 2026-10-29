import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.unit4 import ReplicationCatalog


def test_replication_catalog_records_completed_event():
    catalog = ReplicationCatalog()
    record = catalog.request_replication("EV-001", "CCTV-A", "CCTV-B", file_size=42)
    assert record["status"] == "REPLICATED"
    assert record["replica_node_id"] == "CCTV-B"
    assert catalog.report()["events"][0]["event_type"] == "replication.completed"


def test_replication_rejects_same_owner_and_target():
    catalog = ReplicationCatalog()
    with pytest.raises(ValueError, match="differ"):
        catalog.request_replication("EV-001", "CCTV-A", "CCTV-A")
