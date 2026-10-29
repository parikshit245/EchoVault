# EchoVault — FA-1 Live Demonstration Script

This script provides a step-by-step walkthrough for demonstrating EchoVault during academic evaluation.

---

## Prerequisites
1. Stack running via `docker compose up --build`.
2. Browser open at `http://localhost:3000`.

---

## 11-Step Demonstration Sequence

### Step 1 — System Initialization & Topology Overview
- **Action**: Navigate to `http://localhost:3000/dashboard`.
- **Explain to Examiner**: "EchoVault is running 4 distributed nodes (`CCTV-A`, `CCTV-B`, `SECURITY-A`, `MOBILE-A`), an asynchronous RabbitMQ broker, and a Neon PostgreSQL database. The dashboard shows real-time metrics and an interactive distributed topology map."

### Step 2 — Verify Node Registry
- **Action**: Click on **Nodes** (`/nodes`).
- **Explain**: "Nodes register their logical identity, IP, HTTP port, gRPC port, P2P port, and media capabilities with the registry."

### Step 3 — Incident Context (`INC-000001`)
- **Action**: Navigate to `/incidents/INC-000001`.
- **Explain**: "`INC-000001` represents a Restricted Area Intrusion. Multiple independent nodes have captured observations associated with this shared logical incident."

### Step 4 — Multi-Node Evidence & Ownership
- **Action**: Scroll to the **Attached Multi-Node Evidence** table.
- **Explain**: "Notice the node ownership labels: `EV-001` is owned by `CCTV-A`, `EV-002` by `CCTV-B`, `EV-003` by `SECURITY-A`, and `EV-004` by `MOBILE-A`. Each node maintains private storage; evidence is never merged into a central file dump."

### Step 5 — Synchronous Remote gRPC Retrieval
- **Action**: Click **Fetch via gRPC** next to `EV-002` (owned by `CCTV-B`).
- **Explain**: "The coordinator invokes a synchronous gRPC procedure call (`GetEvidence`) to Node B over HTTP/2 Protobuf. Notice the measured response time (e.g. 12 ms) and metadata returned without direct database access."

### Step 6 — Point-to-Point (P2P) Direct Messaging
- **Action**: Select `CCTV-B` in the **Direct P2P Announcement** tool and click **Send P2P Alert →**.
- **Explain**: "Node A communicates directly with Node B over a dedicated `/ws/peer` WebSocket channel. This message does NOT go through RabbitMQ, demonstrating broker-independent direct peer communication."

### Step 7 — Asynchronous RabbitMQ Event Bus
- **Action**: Navigate to `/messaging`.
- **Explain**: "All system lifecycle events (`evidence.created`, `webrtc.session_*`, `node.status_changed`) are published to the `echovault.events` topic exchange with persistent delivery and consumed asynchronously."

### Step 8 — Stream-Oriented WebSocket Updates
- **Action**: Point out that the messaging table and incident feed update live without refreshing the browser page, backed by the coordinator's `/ws/events` WebSocket stream.

### Step 9 — Real-Time WebRTC Live Multimedia
- **Action**: Navigate to `/live?nodeId=CCTV-A` and click **Start Live WebRTC Session**.
- **Explain**: "The browser initiates SDP signaling over `/ws/webrtc/{session_id}`. Once negotiated, `aiortc` streams live 25 FPS video with a dynamic timestamp clock and audio tone directly to the browser over RTCPeerConnection."

### Step 10 — Fault Simulation & Independence
- **Action**: Navigate to `/system`. Click **Simulate Crash (Offline)** next to `CCTV-B`.
- **Explain**: "`CCTV-B` transitions to OFFLINE. The dashboard updates immediately via WebSocket. Notice that the rest of the system (`CCTV-A`, RabbitMQ, WebRTC) continues operating without degradation."

### Step 11 — Node Recovery
- **Action**: Click **Recover Node (Online)** on `CCTV-B`.
- **Explain**: "`CCTV-B` sends a heartbeat, recovers to ONLINE, and resumes normal distributed operations."

### Step 12 — Lamport Clock and Beacon
- **Action**: Open `/system` and click **Send Beacon**.
- **Explain**: "The beacon is a liveness message that also advances the node's Lamport logical clock. Logical time orders distributed events without depending on wall-clock accuracy."

### Step 13 — Bully Election
- **Action**: Click **Run Bully Election** after `SECURITY-A` is offline.
- **Explain**: "The highest-priority online node becomes coordinator. The election result and logical timestamp are recorded in the Unit 3 coordination panel."

### Step 14 — Mutual Exclusion
- **Action**: Click **Request Incident Lock** twice, then release the first owner.
- **Explain**: "Only one node enters the incident-finalization critical section. The second request waits in a FIFO queue and is promoted after release."

### Step 15 — Global Snapshot
- **Action**: Click **Capture Global Snapshot**.
- **Explain**: "The marker-style snapshot captures each node's local status, logical clock, beacon state, current coordinator, and lock state as one global distributed-system view."

### Step 16 — Evidence Replication and Serverless Function
- **Action**: Click **Replicate Demo Evidence** in the Unit 4 panel.
- **Explain**: "The replication worker records owner, replica, checksum, and status. The completed event models a stateless serverless function triggered by an evidence workflow."
