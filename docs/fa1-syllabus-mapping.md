# EchoVault — FA-1 Syllabus Mapping Guide

This document maps the concepts taught in **Unit 1** and **Unit 2** of the Distributed Systems curriculum directly to concrete implementations in EchoVault.

---

## Unit 1: Introduction to Distributed Systems

### 1. Definition of a Distributed System
- **Theory**: A collection of autonomous computing entities (nodes) that communicate over a network and coordinate their actions by passing messages, appearing to users as a single coherent system.
- **EchoVault Implementation**: 4 independent evidence nodes (`CCTV-A`, `CCTV-B`, `SECURITY-A`, `MOBILE-A`) operate as isolated processes/containers with distinct network addresses. They communicate via gRPC, RabbitMQ, P2P, and WebSockets while presenting a unified incident dashboard to the investigator.

### 2. Goals of Distributed Systems
- **Resource Sharing**: Remote evidence stored on `CCTV-B` is accessible to `CCTV-A` via gRPC without file duplication.
- **Openness & Interoperability**: Uses open standards — Protobuf (gRPC), AMQP 0-9-1 (RabbitMQ), JSON over WebSocket, and WebRTC (RTP/SRTP).
- **Scalability**: New evidence nodes register themselves dynamically with the node registry without requiring coordinator recompilation.
- **Fault Isolation**: Failure of one camera node (`CCTV-B`) does not prevent other nodes from capturing evidence or streaming video.

### 3. Types of Distributed Systems
- **Distributed Information System**: Relational metadata, incident linkage, and evidence indexing across heterogeneous nodes.
- **Distributed Multimedia System**: Real-time live audio and video streaming from distributed camera feeds over WebRTC.
- **Peer-to-Peer Subsystem**: Direct node-to-node point-to-point mesh (`/ws/peer`) without central intermediary routing.

### 4. Distributed System Architecture & Middleware
- **Architecture**: Hybrid Node-Based Multi-Tier Architecture combining decentralized evidence owners with a centralized coordinator and pub/sub message bus.
- **Middleware**:
  - **gRPC**: RPC middleware providing binary serialization, interface definition language (IDL), and client stubs.
  - **RabbitMQ**: Message-oriented middleware providing queuing, durability, routing keys, and dead-lettering.
  - **WebSocket / WebRTC Signaling**: Stream-oriented middleware for real-time coordination.

### 5. Virtualization & Containerization
- **Theory**: Isolation of runtime environments to ensure portability and reproducible distributed node deployment.
- **EchoVault Implementation**: Multi-container deployment managed via `docker-compose.yml` isolating Python 3.12 backends, RabbitMQ brokers, and Next.js frontends.

### 6. Model of Distributed Computation
- **Theory**: Independent processes with local memory and private execution state communicating strictly through message passing over an asynchronous network.
- **EchoVault Implementation**: No shared memory exists between nodes. All state synchronization is achieved through explicit RPC calls, AMQP messages, and WebSocket frames.

---

## Unit 2: Communication in Distributed Systems

### 1. Layered Protocols & Communication Fundamentals
- **Transport vs Application**: Strict separation of HTTP/2 (gRPC), AMQP 0-9-1 (RabbitMQ), WebSocket (RFC 6455), and SRTP (WebRTC).

### 2. Remote Procedure Call (RPC)
- **Implementation**: gRPC with HTTP/2 transport and Protocol Buffers (`proto/evidence_service.proto`).
- **Concepts**: Client stubs, server skeletons, binary serialization, error handling with gRPC status codes (`NOT_FOUND`, `UNAVAILABLE`), and deadline timeouts.

### 3. Message-Oriented Communication
- **Implementation**: RabbitMQ broker utilizing the `echovault.events` topic exchange.
- **Concepts**: Asynchronous message passing, persistent messages (`delivery_mode=2`), exchange-to-queue bindings, consumer acknowledgments (`basic_ack`), and Dead Letter Exchanges (`DLX`).

### 4. Stream-Oriented Communication
- **Implementation**: WebSocket stream (`/ws/events`) for the investigator dashboard.
- **Concepts**: Continuous duplex streaming, subscription filtering (by event type, node, and incident), and connection keep-alive heartbeat.

### 5. Peer-to-Peer Direct Communication
- **Implementation**: Direct node-to-node WebSocket channels (`/ws/peer`).
- **Concepts**: Peer discovery via registry, mutual two-way handshake verification (`HANDSHAKE` / `HANDSHAKE_ACK`), target identity validation, direct ping/pong RTT latency measurement, and message idempotency caches.

### 6. WebRTC & Distributed Multimedia
- **Implementation**: Real-time video/audio streaming via `aiortc` and browser `RTCPeerConnection`.
- **Concepts**: Separation of signaling (`/ws/webrtc/{session_id}`) from media transport (RTP/SRTP), SDP Offer/Answer model, trickle ICE candidate exchange, and dynamic video frame synthesis with timestamp watermarks.

### 7. Names, Identifiers, and Addresses
- **Implementation**: Logical identifiers (`node_id`, `incident_id`, `evidence_id`) separated from physical network addresses (`host:port`, `grpc_host:grpc_port`, `p2p_host:p2p_port`).

### 8. Basic Reliability & Fault Tolerance
- **Implementation**: Structured error handling, gRPC timeouts, RabbitMQ DLX queues, P2P duplicate detection, WebRTC session auto-timeout, and node heartbeat liveness checks.

## Unit 3: Synchronization

### 1. Logical clocks and Lamport's algorithm
- **Implementation**: `POST /api/v1/unit3/clock/tick` advances a Lamport clock for a node. A received clock is merged with `max(local, received) + 1`. The state is visible through `GET /api/v1/unit3/state` and the System Diagnostics Console.

### 2. Clock synchronization
- **Implementation**: `POST /api/v1/unit3/clock/synchronize` demonstrates Cristian's algorithm using a reference time and measured P2P round-trip time. The calculated offset is retained per node without changing the operating-system clock.

### 3. Beacon protocol
- **Implementation**: `POST /api/v1/unit3/beacon` records a node beacon, updates its liveness timestamp, and advances its logical clock. Existing node heartbeats remain the database-backed liveness mechanism.

### 4. Election algorithm
- **Implementation**: `POST /api/v1/unit3/election` runs a deterministic Bully election using node priorities. Taking `SECURITY-A` offline elects `CCTV-A` as the next highest online coordinator.

### 5. Mutual exclusion
- **Implementation**: `POST /api/v1/unit3/lock/request` and `/lock/release` implement coordinator-based mutual exclusion for a shared incident resource. A FIFO request queue promotes the next waiting node when the owner releases the lock.

### 6. Global state
- **Implementation**: `POST /api/v1/unit3/snapshot` captures a marker-style global state containing node status, Lamport clocks, clock offsets, beacons, current leader, and the mutual-exclusion queue.

## Unit 4: Emerging Distributed Paradigms

### 1. Distributed object-based and web-based systems
- **Implementation**: The existing gRPC `NodeService` exposes evidence nodes as remote objects, while the Next.js System Diagnostics Console is a distributed web client over REST and WebSocket APIs.

### 2. Distributed file system concepts
- **Implementation**: `POST /api/v1/unit4/replication/request` records an evidence owner, replica node, checksum, file metadata, and replication status. `GET /api/v1/unit4/replication/{evidence_id}` provides replica lookup/fallback metadata.

### 3. Serverless architecture
- **Implementation**: The replication catalog emits a `replication.completed` event from the stateless `replication_worker` demonstration. This models an event-triggered function without requiring a cloud account.

### 4. Case studies and self-study
- **Documentation scope**: Cloudflare and AWS are used to explain edge/serverless execution; Hadoop is compared with evidence replication; Kubernetes is compared with Docker Compose orchestration. Blockchain and distributed-database trade-offs remain discussion topics rather than unnecessary runtime dependencies.
