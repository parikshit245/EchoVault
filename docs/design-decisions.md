# EchoVault — Architectural Design Decisions (FA-1)

This document records the architectural rationale and trade-off analyses behind key technical decisions in EchoVault.

---

## 1. Why Neon PostgreSQL for Metadata?
* **Decision**: Use Neon PostgreSQL (Serverless PostgreSQL) for node registration, incident linkage, and evidence metadata catalogs.
* **Rationale**: Strong ACID guarantees ensure evidence records, hashes, and node registries remain strictly consistent. Serverless compute allows instant provisioning without local database setup friction.
* **Trade-off**: Requires network access; local raw evidence files remain stored on individual node disks rather than in the central DB.

---

## 2. Why gRPC for Inter-Node RPC?
* **Decision**: Use gRPC with Protocol Buffers (`proto/evidence_service.proto`) for node-to-node queries.
* **Rationale**:
  * **Strong Typing & IDL**: Interface definitions are compiled into client stubs and server skeletons, eliminating schema drift.
  * **Performance**: Binary Protobuf serialization over HTTP/2 multiplexed streams provides lower latency and smaller payload sizes compared to JSON over HTTP/1.1.
  * **Timeouts & Deadlines**: Built-in deadline propagation ensures slow/hung nodes do not exhaust caller resources.

---

## 3. Why RabbitMQ for Asynchronous Messaging?
* **Decision**: Use RabbitMQ with the AMQP 0-9-1 protocol and durable topic exchanges (`echovault.events`).
* **Rationale**:
  * **Temporal Decoupling**: Producing nodes publish events without waiting for consumers to be online.
  * **Routing Flexibility**: Topic routing keys (e.g. `evidence.created`, `webrtc.session_started`) allow fine-grained subscriptions.
  * **Reliability**: Message persistence (`delivery_mode=2`) and Dead Letter Exchanges (DLX) prevent lost telemetry.

---

## 4. Why WebSockets for UI Streams and P2P?
* **Decision**: Use WebSockets for two distinct channels:
  1. `/ws/events`: Coordinator-to-browser live telemetry broadcast.
  2. `/ws/peer`: Direct node-to-node point-to-point mesh.
* **Rationale**:
  * Eliminates HTTP polling overhead for real-time dashboards.
  * Provides bi-directional full-duplex framing for direct node peer links without broker overhead.

---

## 5. Why WebRTC for Multimedia Communication?
* **Decision**: Use WebRTC (`aiortc` + browser `RTCPeerConnection`) with a dedicated signaling channel (`/ws/webrtc/{session_id}`).
* **Rationale**:
  * **Low Latency**: RTP/SRTP over UDP provides sub-second latency for live surveillance feeds.
  * **Separation of Concerns**: Signaling carries session metadata while media travels over dedicated secure RTP channels.
  * **Browser Native**: No third-party plugins or transcoding proxies needed in modern browsers.

---

## 6. Why Docker & Docker Compose?
* **Decision**: Containerize each evidence node (`node-a`, `node-b`), backend coordinator, and frontend.
* **Rationale**:
  * Simulates a true distributed multi-node network with distinct IP addresses, ports, and execution environments on a single developer machine.
