"""
EchoVault FA-1 Demo Seeder Service (Part 10).

Idempotently seeds nodes, incident, associations, and evidence records in the database.
Also provides clean_reset_demo_data to purge all old leftover test records.
"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.evidence import EventType, Evidence, EvidenceType
from ..models.incident import (
    Incident,
    IncidentNode,
    IncidentNodeStatus,
    IncidentRole,
    IncidentSeverity,
    IncidentStatus,
    IncidentType,
)
from ..models.node import Node, NodeStatus, NodeType
from ..models.peer_message import PeerMessage
from ..models.received_message import ReceivedMessage
from ..models.webrtc_session import WebRTCSession

DEMO_NODES = [
    {
        "node_id": "CCTV-A",
        "node_name": "CCTV Camera A — Sector 4 Perimeter",
        "node_type": NodeType.EVIDENCE,
        "host": "localhost",
        "port": 8001,
        "grpc_host": "node-a",
        "grpc_port": 50051,
        "p2p_host": "node-a",
        "p2p_port": 8001,
        "supports_video": True,
        "supports_audio": True,
        "status": NodeStatus.ONLINE,
        "description": "High-definition fixed optical camera with night vision overlooking North Gate.",
    },
    {
        "node_id": "CCTV-B",
        "node_name": "CCTV Camera B — Emergency Exit Corridor",
        "node_type": NodeType.EVIDENCE,
        "host": "localhost",
        "port": 8002,
        "grpc_host": "node-b",
        "grpc_port": 50052,
        "p2p_host": "node-b",
        "p2p_port": 8002,
        "supports_video": True,
        "supports_audio": True,
        "status": NodeStatus.ONLINE,
        "description": "Internal optical surveillance dome monitoring restricted corridor B.",
    },
    {
        "node_id": "SECURITY-A",
        "node_name": "Security Sensor Gateway A",
        "node_type": NodeType.SECURITY,
        "host": "backend",
        "port": 8000,
        "grpc_host": "backend",
        "grpc_port": 50051,
        "p2p_host": "backend",
        "p2p_port": 8000,
        "supports_video": True,
        "supports_audio": False,
        "status": NodeStatus.ONLINE,
        "description": "IoT sensory hub aggregating infrared tripwires and magnetic door contacts.",
    },
    {
        "node_id": "MOBILE-A",
        "node_name": "Mobile Patrol Unit A",
        "node_type": NodeType.MOBILE,
        "host": "localhost",
        "port": 8003,
        "grpc_host": "localhost",
        "grpc_port": 50053,
        "p2p_host": "localhost",
        "p2p_port": 8003,
        "supports_video": True,
        "supports_audio": True,
        "status": NodeStatus.ONLINE,
        "description": "Wearable body-camera and acoustic scanner deployed with on-duty patrol officer.",
    },
    {
        "node_id": "node-docker-001",
        "node_name": "Docker Coordinator Node",
        "node_type": NodeType.COORDINATOR,
        "host": "backend",
        "port": 8000,
        "grpc_host": "backend",
        "grpc_port": 50051,
        "p2p_host": "backend",
        "p2p_port": 8000,
        "supports_video": True,
        "supports_audio": True,
        "status": NodeStatus.ONLINE,
        "description": "Central coordinator and evidence verification service.",
    },
    {
        "node_id": "node-dev-001",
        "node_name": "Local Development Node",
        "node_type": NodeType.COORDINATOR,
        "host": "localhost",
        "port": 8000,
        "grpc_host": "localhost",
        "grpc_port": 50051,
        "p2p_host": "localhost",
        "p2p_port": 8000,
        "supports_video": True,
        "supports_audio": True,
        "status": NodeStatus.ONLINE,
        "description": "Local workstation development coordinator instance.",
    },
]

DEMO_INCIDENT = {
    "incident_id": "INC-000001",
    "title": "Restricted Area Intrusion",
    "description": "Multi-sensor intrusion alarm triggered in Sector 4. CCTV cameras and mobile patrol units dispatched to investigate unauthorized perimeter breach.",
    "incident_type": IncidentType.SECURITY,
    "severity": IncidentSeverity.HIGH,
    "status": IncidentStatus.OPEN,
    "created_by_node_id": "CCTV-A",
    "location": {"sector": "Sector 4", "zone": "North Perimeter", "building": "Building B"},
}

DEMO_EVIDENCE = [
    {
        "evidence_id": "EV-001",
        "node_id": "CCTV-A",
        "incident_id": "INC-000001",
        "title": "Unauthorized personnel detected in Sector 4",
        "description": "Optical bounding box trigger detecting masked individual crossing restricted fence line.",
        "event_type": EventType.PERSON_DETECTED,
        "evidence_type": EvidenceType.IMAGE,
        "file_path": "storage/evidence/CCTV-A/EV-001.jpg",
        "file_size": 1048576,
        "metadata_json": {"sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"},
    },
    {
        "evidence_id": "EV-002",
        "node_id": "CCTV-B",
        "incident_id": "INC-000001",
        "title": "Emergency exit door forced open",
        "description": "CCTV-B capture showing forced entry through corridor emergency door 4B.",
        "event_type": EventType.DOOR_OPENED,
        "evidence_type": EvidenceType.IMAGE,
        "file_path": "storage/evidence/CCTV-B/EV-002.jpg",
        "file_size": 2097152,
        "metadata_json": {"sha256": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a"},
    },
    {
        "evidence_id": "EV-003",
        "node_id": "SECURITY-A",
        "incident_id": "INC-000001",
        "title": "IR perimeter tripwire trigger",
        "description": "Digital log stream from photoelectric barrier registering physical breach event.",
        "event_type": EventType.MOTION_DETECTED,
        "evidence_type": EvidenceType.SENSOR,
        "file_path": "storage/evidence/SECURITY-A/EV-003.log",
        "file_size": 524288,
        "metadata_json": {"sha256": "ef2d127de37b942baad06145e54b0c619a1f22327b2ebbcfbec78f5564afe39d"},
    },
    {
        "evidence_id": "EV-004",
        "node_id": "MOBILE-A",
        "incident_id": "INC-000001",
        "title": "Acoustic glass-break frequency match",
        "description": "Audio spectrum telemetry detecting high-frequency impact signature consistent with shattered glass.",
        "event_type": EventType.AUDIO_DETECTED,
        "evidence_type": EvidenceType.AUDIO,
        "file_path": "storage/evidence/MOBILE-A/EV-004.wav",
        "file_size": 4194304,
        "metadata_json": {"sha256": "8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918"},
    },
]


async def seed_demo_data(session: AsyncSession) -> dict[str, int]:
    """Idempotently seeds nodes, incident, associations, and evidence records."""
    now = datetime.now(timezone.utc)
    seeded_counts = {"nodes": 0, "incidents": 0, "incident_nodes": 0, "evidence": 0}

    # 1. Seed Nodes
    for n_data in DEMO_NODES:
        stmt = select(Node).where(Node.node_id == n_data["node_id"])
        res = await session.execute(stmt)
        existing = res.scalar_one_or_none()
        if existing:
            for k, v in n_data.items():
                setattr(existing, k, v)
            existing.last_seen_at = now
        else:
            node = Node(**n_data)
            node.last_seen_at = now
            session.add(node)
            seeded_counts["nodes"] += 1

    await session.commit()

    # 2. Seed Incident
    inc_stmt = select(Incident).where(Incident.incident_id == DEMO_INCIDENT["incident_id"])
    inc_res = await session.execute(inc_stmt)
    incident = inc_res.scalar_one_or_none()
    if not incident:
        incident = Incident(
            **DEMO_INCIDENT,
            started_at=now,
            created_at=now,
        )
        session.add(incident)
        seeded_counts["incidents"] += 1
        await session.commit()

    # 3. Associate Nodes with Incident
    for n_data in DEMO_NODES:
        assoc_stmt = select(IncidentNode).where(
            IncidentNode.incident_id == DEMO_INCIDENT["incident_id"],
            IncidentNode.node_id == n_data["node_id"],
        )
        assoc_res = await session.execute(assoc_stmt)
        if not assoc_res.scalar_one_or_none():
            assoc = IncidentNode(
                incident_id=DEMO_INCIDENT["incident_id"],
                node_id=n_data["node_id"],
                role=IncidentRole.OBSERVER,
                status=IncidentNodeStatus.ACTIVE,
                joined_at=now,
            )
            session.add(assoc)
            seeded_counts["incident_nodes"] += 1

    await session.commit()

    # 4. Seed Evidence Records
    for ev_data in DEMO_EVIDENCE:
        ev_stmt = select(Evidence).where(Evidence.evidence_id == ev_data["evidence_id"])
        ev_res = await session.execute(ev_stmt)
        existing_ev = ev_res.scalar_one_or_none()
        if not existing_ev:
            ev = Evidence(
                **ev_data,
                captured_at=now,
                created_at=now,
            )
            session.add(ev)
            seeded_counts["evidence"] += 1

    await session.commit()
    return seeded_counts


async def clean_reset_demo_data(session: AsyncSession) -> dict[str, int]:
    """
    Purges all old leftover nodes, evidence, sessions, and messages,
    then cleanly re-seeds only the 4 canonical FA-1 demo nodes.
    """
    # Delete in reverse foreign key order
    await session.execute(delete(PeerMessage))
    await session.execute(delete(ReceivedMessage))
    await session.execute(delete(WebRTCSession))
    await session.execute(delete(Evidence))
    await session.execute(delete(IncidentNode))
    await session.execute(delete(Incident))
    await session.execute(delete(Node))
    await session.commit()

    # Re-seed the clean demo environment
    counts = await seed_demo_data(session)
    return counts
