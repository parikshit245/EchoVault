"""In-memory evidence replication catalog and event-driven function demo."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any


class ReplicationCatalog:
    def __init__(self) -> None:
        self.records: dict[str, dict[str, Any]] = {}
        self.events: list[dict[str, Any]] = []

    def reset(self) -> None:
        self.records.clear()
        self.events.clear()

    def request_replication(
        self,
        evidence_id: str,
        owner_node_id: str,
        target_node_id: str,
        *,
        file_name: str | None = None,
        file_size: int | None = None,
        checksum: str | None = None,
    ) -> dict[str, Any]:
        if owner_node_id == target_node_id:
            raise ValueError("Replica target must differ from the owner")
        record = {
            "replication_id": f"REPL-{uuid.uuid4().hex[:8].upper()}",
            "evidence_id": evidence_id,
            "owner_node_id": owner_node_id,
            "replica_node_id": target_node_id,
            "file_name": file_name,
            "file_size": file_size,
            "checksum": checksum or hashlib.sha256(evidence_id.encode()).hexdigest(),
            "status": "REPLICATED",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.records[evidence_id] = record
        self.events.insert(
            0,
            {
                "event_type": "replication.completed",
                "function": "replication_worker",
                "event_id": f"FUNC-{uuid.uuid4().hex[:8].upper()}",
                "evidence_id": evidence_id,
                "status": "completed",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        return record

    def get(self, evidence_id: str) -> dict[str, Any] | None:
        return self.records.get(evidence_id)

    def report(self) -> dict[str, Any]:
        return {
            "catalog": list(self.records.values()),
            "events": self.events[:20],
            "functions": ["replication_worker", "fallback_retrieval"],
        }


replication_catalog = ReplicationCatalog()
