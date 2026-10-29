"""Small, deterministic demonstrations of the Unit 3 algorithms.

The coordinator exposes this state through ``routers.unit3``.  The algorithms
are intentionally kept independent from the database so they can be reset and
demonstrated without a migration or a running broker.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any


DEFAULT_NODES = {
    "SECURITY-A": 4,
    "CCTV-A": 3,
    "CCTV-B": 2,
    "MOBILE-A": 1,
}


class Unit3State:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self.nodes: dict[str, dict[str, Any]] = {}
        self.clock = 0
        self.leader: str | None = None
        self.election_history: list[dict[str, Any]] = []
        self.lock_owner: str | None = None
        self.lock_resource: str | None = None
        self.lock_queue: deque[str] = deque()
        self.beacons: dict[str, dict[str, Any]] = {}
        self.last_snapshot: dict[str, Any] | None = None
        self.reset()

    def reset(self) -> None:
        self.clock = 0
        self.leader = "SECURITY-A"
        self.lock_owner = None
        self.lock_resource = None
        self.lock_queue.clear()
        self.election_history.clear()
        self.beacons.clear()
        self.last_snapshot = None
        self.nodes = {
            node_id: {
                "node_id": node_id,
                "priority": priority,
                "status": "ONLINE",
                "lamport_clock": 0,
                "clock_offset_ms": 0.0,
                "last_beacon_at": None,
                "last_event": "RESET",
            }
            for node_id, priority in DEFAULT_NODES.items()
        }

    def tick(self, node_id: str | None = None, received_clock: int | None = None) -> int:
        self.clock = max(self.clock, received_clock or 0) + 1
        if node_id in self.nodes:
            self.nodes[node_id]["lamport_clock"] = max(
                self.nodes[node_id]["lamport_clock"], self.clock
            )
            self.nodes[node_id]["last_event"] = "LAMPORT_TICK"
        return self.clock

    def beacon(self, node_id: str) -> dict[str, Any]:
        if node_id not in self.nodes:
            raise KeyError(node_id)
        logical = self.tick(node_id)
        now = datetime.now(timezone.utc).isoformat()
        self.beacons[node_id] = {"node_id": node_id, "received_at": now, "lamport_clock": logical}
        self.nodes[node_id]["last_beacon_at"] = now
        self.nodes[node_id]["status"] = "ONLINE"
        self.nodes[node_id]["last_event"] = "BEACON"
        return self.beacons[node_id]

    def synchronize(self, node_id: str, reference_time_ms: float, round_trip_ms: float) -> dict[str, Any]:
        if node_id not in self.nodes:
            raise KeyError(node_id)
        local_midpoint = time.time() * 1000 - round_trip_ms / 2
        offset = round(reference_time_ms - local_midpoint, 2)
        self.nodes[node_id]["clock_offset_ms"] = offset
        self.nodes[node_id]["last_event"] = "CRISTIAN_SYNC"
        return {"node_id": node_id, "offset_ms": offset, "round_trip_ms": round(round_trip_ms, 2)}

    def elect(self, failed_node_id: str | None = None) -> dict[str, Any]:
        if failed_node_id in self.nodes:
            self.nodes[failed_node_id]["status"] = "OFFLINE"
        candidates = [
            node for node in self.nodes.values() if node["status"] == "ONLINE"
        ]
        if not candidates:
            self.leader = None
        else:
            self.leader = max(candidates, key=lambda node: node["priority"])["node_id"]
        logical = self.tick(self.leader)
        result = {
            "election_id": f"ELECT-{uuid.uuid4().hex[:8].upper()}",
            "leader": self.leader,
            "failed_node": failed_node_id,
            "algorithm": "BULLY",
            "lamport_clock": logical,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        self.election_history.insert(0, result)
        return result

    def request_lock(self, node_id: str, resource_id: str) -> dict[str, Any]:
        if node_id not in self.nodes or self.nodes[node_id]["status"] != "ONLINE":
            raise ValueError("Requesting node is not online")
        if self.lock_owner is None:
            self.lock_owner, self.lock_resource = node_id, resource_id
            granted = True
        else:
            granted = False
            if node_id not in self.lock_queue:
                self.lock_queue.append(node_id)
        self.tick(node_id)
        return {
            "resource_id": resource_id,
            "owner_node_id": self.lock_owner,
            "requested_by": node_id,
            "granted": granted,
            "queue": list(self.lock_queue),
            "algorithm": "COORDINATOR_MUTEX",
        }

    def release_lock(self, node_id: str) -> dict[str, Any]:
        if self.lock_owner != node_id:
            raise ValueError("Only the lock owner can release the lock")
        previous_resource = self.lock_resource
        self.lock_owner = None
        self.lock_resource = None
        if self.lock_queue:
            self.lock_owner = self.lock_queue.popleft()
            self.lock_resource = previous_resource
        self.tick(node_id)
        return {
            "released_by": node_id,
            "owner_node_id": self.lock_owner,
            "resource_id": self.lock_resource,
            "queue": list(self.lock_queue),
        }

    def snapshot(self) -> dict[str, Any]:
        snapshot = {
            "snapshot_id": f"SNAP-{uuid.uuid4().hex[:8].upper()}",
            "algorithm": "MARKER_BASED_GLOBAL_STATE",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "leader": self.leader,
            "lamport_clock": self.clock,
            "lock": {
                "owner_node_id": self.lock_owner,
                "resource_id": self.lock_resource,
                "queue": list(self.lock_queue),
            },
            "nodes": {node_id: dict(node) for node_id, node in self.nodes.items()},
        }
        self.last_snapshot = snapshot
        return snapshot

    def report(self) -> dict[str, Any]:
        return {
            "leader": self.leader,
            "lamport_clock": self.clock,
            "nodes": list(self.nodes.values()),
            "lock": {
                "owner_node_id": self.lock_owner,
                "resource_id": self.lock_resource,
                "queue": list(self.lock_queue),
            },
            "beacons": list(self.beacons.values()),
            "elections": self.election_history[:10],
            "last_snapshot": self.last_snapshot,
        }


unit3_state = Unit3State()
