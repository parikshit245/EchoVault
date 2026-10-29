# EchoVault Implementation Report

**Prepared:** 29 October 2026  
**Repository:** `parikshit245/EchoVault`  
**Project:** Distributed Digital Evidence Collection, Incident Reconstruction, and Real-Time Multimedia Streaming System  
**Report scope:** The implementation currently present in this working tree, including backend, frontend, persistence, distributed communication, demo features, tests, and deployment configuration.

> This report describes implemented code and verified build/test results. It distinguishes working code from design intentions, demo-only state, and deployment limitations.

---

## 1. Executive Summary

EchoVault is implemented as a multi-service distributed-systems demonstration. It models independently configured evidence nodes that retain local evidence ownership while cooperating through several communication mechanisms:

- REST/HTTP and JSON for browser-to-service operations.
- gRPC over HTTP/2 and Protocol Buffers for synchronous inter-node RPC.
- RabbitMQ/AMQP for asynchronous event publication and consumption.
- Browser WebSockets for live event delivery.
- Direct peer-to-peer WebSockets for node-to-node control and announcements.
- WebRTC signaling and RTP/SRTP media for live demo video and audio.

The backend is a FastAPI application whose behavior changes through environment configuration. The same image can run as a coordinator, CCTV evidence node, security node, or mobile node. PostgreSQL stores registry, evidence metadata, incident metadata, message records, and WebRTC session records. Raw evidence files are stored in node-local mounted storage.

The frontend is a Next.js 16 / React 19 command center with pages for the dashboard, evidence, incidents, nodes, peers, messaging, live WebRTC media, and system diagnostics.

The project also includes educational Unit 3 and Unit 4 demonstrations:

- Lamport clocks, Cristian clock synchronization, Bully election, coordinator mutual exclusion, and marker-based global snapshots.
- An event-driven in-memory evidence replication catalog and serverless-function-style workflow.

### Current verification result

| Area | Result |
|---|---|
| Backend automated tests | **110 passed, 1 skipped** |
| Backend test duration | 215.48 seconds |
| Frontend production build | **Passed** |
| Frontend TypeScript check | Completed successfully as part of the build |
| Frontend ESLint | **0 errors, 6 warnings** |
| Docker Compose configuration | Present and defines RabbitMQ, backend, two evidence nodes, and frontend |

---

## 2. Repository Structure

### 2.1 Major directories and files

| Location | Implemented responsibility |
|---|---|
| [`services/node/`](services/node/) | Python backend service and node runtime |
| [`services/node/app/main.py`](services/node/app/main.py) | FastAPI application, lifecycle startup/shutdown, router registration |
| [`services/node/app/routers/`](services/node/app/routers/) | REST, WebSocket, gRPC-facing, demo, P2P, and WebRTC endpoints |
| [`services/node/app/models/`](services/node/app/models/) | SQLAlchemy persistence models |
| [`services/node/app/schemas/`](services/node/app/schemas/) | Pydantic request/response validation models |
| [`services/node/app/messaging/`](services/node/app/messaging/) | RabbitMQ connection, publisher, consumer, event schemas, handlers |
| [`services/node/app/p2p/`](services/node/app/p2p/) | Peer protocol, connections, manager, idempotency, and peer lifecycle |
| [`services/node/app/webrtc/`](services/node/app/webrtc/) | WebRTC session manager, signaling schemas, demo tracks |
| [`services/node/app/grpc/`](services/node/app/grpc/) | Protobuf-generated code, server, handlers, and RPC clients |
| [`services/node/alembic/versions/`](services/node/alembic/versions/) | Database migrations from node registry through WebRTC support |
| [`services/node/tests/`](services/node/tests/) | Unit, integration, endpoint, communication, and end-to-end tests |
| [`frontend/src/app/`](frontend/src/app/) | Next.js App Router pages |
| [`frontend/src/components/`](frontend/src/components/) | Shared navigation, mission, and WebRTC UI components |
| [`frontend/src/hooks/`](frontend/src/hooks/) | Browser event-stream and WebRTC session hooks |
| [`scripts/`](scripts/) | Root demo seeding and database reset wrappers |
| [`docs/`](docs/) | Architecture, design decisions, FA-1 mapping, demo script, and viva material |
| [`docker-compose.yml`](docker-compose.yml) | Local multi-container deployment |
| [`services/node/requirements.txt`](services/node/requirements.txt) | Python runtime and test dependencies |
| [`frontend/package.json`](frontend/package.json) | Frontend scripts and JavaScript dependencies |

The repository also contains [`PROJECT_DOCUMENTATION.md`](PROJECT_DOCUMENTATION.md), the existing long-form project documentation. This report is an implementation-focused snapshot rather than a replacement for that document.

---

## 3. Backend Application

### 3.1 Application startup and shutdown

[`services/node/app/main.py`](services/node/app/main.py) creates the FastAPI application and registers all service routers. Its lifespan performs the following operations:

1. Starts the gRPC server.
2. Attempts to connect the RabbitMQ publisher connection.
3. Starts the RabbitMQ consumer and its queue/bindings.
4. Self-registers the configured node in the shared database.
5. On shutdown, stops gRPC, stops the consumer, closes RabbitMQ, closes P2P connections, and closes WebRTC sessions.

RabbitMQ connection failure is intentionally non-fatal during startup so the HTTP service can still expose health and direct-communication functionality. The application adds request-context middleware and CORS middleware configured from environment settings.

### 3.2 Configuration

[`services/node/app/config.py`](services/node/app/config.py) and [`.env.example`](.env.example) define configurable values for:

- HTTP host and port.
- PostgreSQL connection URL.
- Logical node identity, type, host, and port.
- gRPC bind and discovery addresses.
- gRPC request timeout.
- RabbitMQ host, port, credentials, vhost, exchange, TTL, and retry limit.
- P2P host, port, and reconnect backoff.
- WebRTC STUN server.
- Demo media mode and audio/video capability flags.
- Evidence storage directory and upload size limit.

The service is therefore reusable for multiple logical nodes without changing application code.

### 3.3 Persistence model

The SQLAlchemy models implement the following concepts:

- **Node:** logical node identity, type, HTTP address, gRPC address, P2P address, capabilities, status, timestamps, and liveness.
- **Evidence:** evidence metadata, owner node, incident associations, file metadata, checksum/type information, and soft-deletion state.
- **Incident:** incident identifier, type, severity, status, description, timestamps, and associations.
- **IncidentNode:** participating nodes, roles, status, and active/inactive membership.
- **ReceivedMessage:** consumed message identity, source node, event type, processing status, and error information.
- **WebRTCSession:** session identity, source node, requester, media options, status, timestamps, and failure information.

The migration sequence in [`services/node/alembic/versions/`](services/node/alembic/versions/) includes:

1. Node registry.
2. Evidence metadata.
3. Incidents and incident relationships.
4. gRPC address fields.
5. Received-message persistence.
6. P2P fields.
7. WebRTC support.
8. Node-scoped uniqueness for received message IDs.

The latest migration is [`0008_scope_received_message_id_per_node.py`](services/node/alembic/versions/0008_scope_received_message_id_per_node.py). This allows the same message identifier to be handled independently by different nodes while preserving duplicate protection within each node.

---

## 4. REST API Capabilities

All REST API resources are versioned under `/api/v1` unless noted otherwise.

### 4.1 Health and identity

Implemented in [`services/node/app/routers/health.py`](services/node/app/routers/health.py) and [`services/node/app/routers/identity.py`](services/node/app/routers/identity.py):

- `GET /` — basic service response.
- `GET /health` — overall health.
- `GET /health/database` — database health.
- `GET /health/messaging` — RabbitMQ/messaging health.
- `GET /health/websocket` — browser WebSocket manager health.
- `GET /health/p2p` — peer manager health.
- `GET /health/webrtc` — WebRTC manager health.
- `GET /api/v1/node/self` — current configured node identity.
- `POST /api/v1/node/self/register` — explicitly register the current node.

### 4.2 Node registry

Implemented in [`services/node/app/routers/nodes.py`](services/node/app/routers/nodes.py):

- `POST /api/v1/nodes` — register a node.
- `GET /api/v1/nodes` — discover registered nodes.
- `GET /api/v1/nodes/{node_id}` — retrieve one node.
- `PATCH /api/v1/nodes/{node_id}` — update metadata/status.
- `POST /api/v1/nodes/{node_id}/heartbeat` — record liveness.
- `DELETE /api/v1/nodes/{node_id}` — deactivate a node.

Startup self-registration updates the current host, port, status, and last-seen timestamp, which is especially important when the browser must reach a node through Docker-published ports.

### 4.3 Local evidence

Implemented in [`services/node/app/routers/evidence.py`](services/node/app/routers/evidence.py):

- `POST /api/v1/evidence` — create local evidence metadata.
- `GET /api/v1/evidence` — list evidence owned by the current node.
- `POST /api/v1/evidence/upload` — upload a local evidence file.
- `GET /api/v1/evidence/{evidence_id}` — retrieve local evidence metadata.
- `PATCH /api/v1/evidence/{evidence_id}` — update metadata.
- `DELETE /api/v1/evidence/{evidence_id}` — soft-delete evidence.
- `GET /api/v1/evidence/{evidence_id}/file` — download the local file.

Evidence access is ownership-aware. The local service does not directly read another node’s storage directory.

### 4.4 Incidents and correlation

Implemented in [`services/node/app/routers/incidents.py`](services/node/app/routers/incidents.py):

- Create, list, retrieve, and update incidents.
- Attach and remove local evidence.
- List evidence linked to an incident.
- Add, list, and deactivate participating nodes.

This provides a shared logical investigation context while preserving local evidence ownership.

### 4.5 Remote RPC-backed access

Implemented in [`services/node/app/routers/remote.py`](services/node/app/routers/remote.py):

- `GET /api/v1/remote/nodes/{node_id}/status`
- `GET /api/v1/remote/nodes/{node_id}/evidence/{evidence_id}`
- `GET /api/v1/remote/nodes/{node_id}/incidents/{incident_id}/evidence`

These endpoints use the gRPC client rather than reading another node’s database or filesystem directly. Timeout and unavailable-node paths return controlled errors.

---

## 5. Distributed Communication Implementations

### 5.1 gRPC

The gRPC implementation is under [`services/node/app/grpc/`](services/node/app/grpc/) and uses generated code from the project Protocol Buffer definition.

Implemented behavior includes:

- A gRPC server started for every service instance.
- Typed node status and evidence retrieval RPCs.
- Remote incident evidence retrieval.
- Configurable bind address, advertised address, and timeout.
- Client-side error handling for unavailable or timed-out nodes.
- Generated Python stubs and servicer classes.

This is the synchronous request/response path for remote node data.

### 5.2 RabbitMQ messaging

The messaging implementation is under [`services/node/app/messaging/`](services/node/app/messaging/).

Implemented features:

- Robust RabbitMQ connection management using `aio-pika`.
- Topic exchange configuration through `RABBITMQ_EXCHANGE`.
- Event envelope validation with Pydantic.
- Typed payloads for evidence, incident, node, test, and WebRTC lifecycle events.
- Per-node consumer queue and event bindings.
- Retry/requeue behavior controlled by `RABBITMQ_RETRY_LIMIT`.
- Message TTL configuration.
- Received-message persistence and idempotency.
- Handler dispatch for known event types.
- Dead/failure handling paths instead of silent success.

Important event families include:

- `evidence.created`
- `evidence.updated`
- `evidence.deleted`
- `incident.created`
- `incident.updated`
- `incident.closed`
- `evidence.associated`
- `evidence.removed`
- `node.registered`
- `node.status_changed`
- `webrtc.session_requested`
- `webrtc.session_started`
- `webrtc.session_ended`
- `webrtc.session_failed`

### 5.3 Browser WebSocket event stream

[`services/node/app/routers/websocket.py`](services/node/app/routers/websocket.py), the WebSocket manager, and [`frontend/src/hooks/useEventStream.ts`](frontend/src/hooks/useEventStream.ts) implement the live dashboard event stream:

- Browser clients connect to `/ws/events`.
- Clients can subscribe to filtered event streams.
- The backend broadcasts accepted messaging events to connected clients.
- The frontend tracks connection state, live events, connection ID, and reconnect behavior.
- The messaging page shows live messages without page refresh.

WebSocket delivery occurs after message acknowledgement so a dashboard delivery failure does not cause a successfully processed RabbitMQ message to be requeued.

### 5.4 Direct P2P WebSockets

The P2P implementation is under [`services/node/app/p2p/`](services/node/app/p2p/) and [`services/node/app/routers/p2p.py`](services/node/app/routers/p2p.py).

Implemented operations:

- `WS /ws/peer` — peer handshake and message channel.
- `GET /api/v1/peers` — list peer states.
- `POST /api/v1/peers/{node_id}/connect` — establish a peer connection.
- `POST /api/v1/peers/{node_id}/disconnect` — close a peer connection.
- `POST /api/v1/peers/{node_id}/ping` — measure peer round-trip liveness.
- `POST /api/v1/peers/{node_id}/message` — send direct application data.
- `POST /api/v1/peers/{node_id}/announce/evidence/{evidence_id}` — announce evidence.
- `POST /api/v1/peers/{node_id}/announce/incident/{incident_id}` — announce incident activity.
- `GET /api/v1/peers/messages` — inspect received peer messages.

The protocol contains handshake, handshake acknowledgement, ping/pong, generic message, evidence announcement, and incident announcement payloads. Message IDs and the idempotency cache prevent duplicate processing. Peer identity mismatch and disconnected-peer errors are surfaced explicitly.

### 5.5 WebRTC multimedia

The WebRTC implementation is under [`services/node/app/webrtc/`](services/node/app/webrtc/), [`services/node/app/routers/webrtc.py`](services/node/app/routers/webrtc.py), and [`frontend/src/hooks/useWebRTCSession.ts`](frontend/src/hooks/useWebRTCSession.ts).

Implemented behavior:

- Session creation targeted at a configured evidence node.
- Media option validation for video/audio.
- WebSocket signaling at `/ws/webrtc/{session_id}`.
- SDP offer/answer handling.
- ICE candidate signaling.
- Session lifecycle tracking and cleanup.
- Timeout and unavailable-node handling.
- Lifecycle event publication.
- Demo video track with surveillance-style timestamp/HUD output.
- Demo audio track.
- Browser `RTCPeerConnection` integration through the live feed component.

The media is deterministic demo media rather than a physical camera integration. The design separates signaling (WebSocket) from media transport (WebRTC RTP/SRTP).

---

## 6. Unit 3 Distributed-Systems Demonstrations

Unit 3 is implemented as an in-memory deterministic state machine in [`services/node/app/unit3.py`](services/node/app/unit3.py), exposed through [`services/node/app/routers/unit3.py`](services/node/app/routers/unit3.py).

### 6.1 Lamport logical clocks

- Maintains a global logical clock and per-node clock values.
- Supports local ticks.
- Supports updates from received logical-clock values.
- Records the last logical event for each demo node.

Endpoints:

- `GET /api/v1/unit3/state`
- `POST /api/v1/unit3/clock/tick`

### 6.2 Cristian clock synchronization

`POST /api/v1/unit3/clock/synchronize` estimates clock offset using a reference time and round-trip duration. The calculated offset is stored in the simulated node state.

### 6.3 Heartbeat/beacon state

`POST /api/v1/unit3/beacon` records node liveness, receipt timestamp, and the logical clock at which the beacon was observed.

### 6.4 Bully leader election

`POST /api/v1/unit3/election` can mark a failed node offline and elect the highest-priority online node. The result contains:

- Election ID.
- Selected leader.
- Failed node, if any.
- Algorithm name.
- Lamport clock.
- Completion timestamp.

### 6.5 Coordinator mutual exclusion

The lock endpoints implement a coordinator-based mutex:

- `POST /api/v1/unit3/lock/request`
- `POST /api/v1/unit3/lock/release`

The first valid requester receives the lock; later requesters enter a FIFO queue. Only the current owner can release it, and the next queued node becomes owner.

### 6.6 Marker-based global snapshot

`POST /api/v1/unit3/snapshot` captures the simulated leader, Lamport clock, lock state, queue, and node states as a snapshot record.

### 6.7 Reset

`POST /api/v1/unit3/reset` returns the demonstration to its default four-node state.

These algorithms are deliberately isolated from the database and broker so they can be reset and demonstrated independently.

---

## 7. Unit 4 Evidence Replication Demonstration

Unit 4 is implemented in [`services/node/app/unit4.py`](services/node/app/unit4.py) and [`services/node/app/routers/unit4.py`](services/node/app/routers/unit4.py).

The `ReplicationCatalog` records:

- Evidence ID.
- Owner node.
- Replica target node.
- File name and size.
- Checksum.
- Replication ID and timestamp.
- Replication status.

`POST /api/v1/unit4/replication/request` rejects an owner and target that are the same, creates a deterministic fallback checksum when one is not supplied, and emits a `replication.completed` function-style event.

Additional endpoints:

- `GET /api/v1/unit4/state`
- `GET /api/v1/unit4/replication/{evidence_id}`
- `POST /api/v1/unit4/reset`

This is a catalog/event demonstration, not a byte-for-byte distributed file transfer implementation. The catalog is in memory and is reset when the service process restarts.

---

## 8. Frontend Command Center

The frontend uses Next.js App Router, React, TypeScript, and shared components under [`frontend/src/components/`](frontend/src/components/).

### 8.1 Implemented routes

| Route | Purpose |
|---|---|
| `/` | Landing page and project overview |
| `/dashboard` | Unified operations dashboard |
| `/evidence` | Evidence listing and inspection |
| `/incidents` | Incident list and controls |
| `/incidents/[incidentId]` | Dynamic incident command view |
| `/live` | WebRTC live multimedia stage |
| `/messaging` | RabbitMQ/WebSocket message monitor |
| `/nodes` | Node registry and health view |
| `/peers` | Direct P2P peer manager |
| `/system` | System health and diagnostics |

The production build generated all eleven application routes successfully.

### 8.2 Shared UI

- [`HeaderNav.tsx`](frontend/src/components/HeaderNav.tsx) provides application navigation.
- [`GuidedMission.tsx`](frontend/src/components/GuidedMission.tsx) supports the guided FA-1 demonstration flow.
- [`LiveWebRTCFeed.tsx`](frontend/src/components/LiveWebRTCFeed.tsx) manages node selection, session start/stop, media rendering, and session status.
- [`useEventStream.ts`](frontend/src/hooks/useEventStream.ts) handles WebSocket connection and event updates.
- [`useWebRTCSession.ts`](frontend/src/hooks/useWebRTCSession.ts) handles WebRTC session creation, signaling, ICE, media stream state, and cleanup.

### 8.3 Frontend data integration

The UI reads `NEXT_PUBLIC_BACKEND_URL` and calls the backend REST endpoints for:

- Nodes and node health.
- Evidence.
- Incidents and incident evidence.
- Messaging records and messaging health.
- Peer connections and peer messages.
- Unit 3 synchronization state.
- Unit 4 replication state.
- WebRTC session setup and signaling.

The messaging and dashboard surfaces are designed for continuous updates rather than requiring manual refresh.

---

## 9. Demo and Operational Controls

The demo router in [`services/node/app/routers/demo.py`](services/node/app/routers/demo.py) and the seeder in [`services/node/app/services/demo_seeder.py`](services/node/app/services/demo_seeder.py) provide reproducible demonstration controls:

- `POST /api/v1/demo/seed` — seed the FA-1 scenario.
- `POST /api/v1/demo/simulate/node-status` — simulate node failure or recovery.
- `POST /api/v1/demo/simulate/event` — inject a custom distributed event.
- `POST /api/v1/demo/reset` — reset demonstration data/state.

The root wrapper [`scripts/seed_demo.py`](scripts/seed_demo.py) makes the seeder runnable from the repository root. [`scripts/reset_db.py`](scripts/reset_db.py) provides a database reset helper.

The demonstration scenario is centered on a shared incident and multiple logical evidence-producing nodes. It is intended to show local ownership, incident correlation, asynchronous event propagation, remote RPC access, peer messaging, and live media.

---

## 10. Deployment and Runtime Topology

[`docker-compose.yml`](docker-compose.yml) defines:

### 10.1 RabbitMQ

- RabbitMQ 3.13 management image.
- AMQP port `5672`.
- Management UI port `15672`.
- Persistent `rabbitmq_data` volume.
- Health check with `rabbitmq-diagnostics ping`.

### 10.2 Coordinator backend

- Builds from [`services/node/Dockerfile`](services/node/Dockerfile).
- Publishes HTTP port `8000`.
- Uses gRPC port `50051` internally.
- Uses the `backend` service name for container-to-container gRPC/P2P.
- Uses persistent `evidence_storage`.
- Depends on healthy RabbitMQ.

### 10.3 Evidence nodes

Two independently configured service instances are defined:

- `node-a`: logical `CCTV-A`, HTTP `8001`, gRPC `50051`, P2P `8001`.
- `node-b`: logical `CCTV-B`, HTTP `8002`, gRPC `50052`, P2P `8002`.

Each has its own evidence volume and published HTTP/gRPC ports.

### 10.4 Frontend

- Builds from [`frontend/`](frontend/).
- Publishes port `3000`.
- Uses `NEXT_PUBLIC_BACKEND_URL=http://localhost:8000`.

### 10.5 Deployment interpretation

The compose file starts the coordinator, two evidence nodes, RabbitMQ, and the UI. `SECURITY-A` and `MOBILE-A` are represented by the logical model and demo state but are not separate compose services in the current file. They can be run as additional instances of the same backend image with distinct environment values.

---

## 11. Testing and Verification

### 11.1 Backend test suite

Command executed:

```powershell
.\.venv\Scripts\python.exe -m pytest services\node\tests -q
```

Result:

```text
110 passed, 1 skipped, 3 warnings in 215.48s
```

The test inventory covers:

- Basic API behavior.
- Node and incident rules.
- gRPC contracts and two-node integration.
- RabbitMQ publisher, consumer, health, and idempotency.
- Browser WebSocket endpoints, manager behavior, event streaming, and filtering.
- P2P endpoint, protocol, manager, and idempotency.
- WebRTC endpoint, manager, signaling, and media tracks.
- Unit 3 and Unit 4 demonstrations.
- An end-to-end distributed workflow.

### 11.2 Frontend lint

Command executed from `frontend`:

```powershell
npm run lint
```

Result:

```text
0 errors, 6 warnings
```

The warnings are:

1. A missing `loadData` dependency in the live page effect.
2. Three unused imports/variables in the nodes page.
3. One unused `Link` import in the peers page.
4. One unused ESLint disable directive in `useEventStream.ts`.

These warnings do not prevent the lint command from completing successfully, but they are cleanup items for a future revision.

### 11.3 Frontend production build

Command executed from `frontend`:

```powershell
npm run build
```

Result:

- Next.js 16.3.2 build completed successfully.
- TypeScript completed successfully.
- Static page generation completed for all generated pages.
- All listed frontend routes were produced.

### 11.4 Test warnings and observations

The backend run emitted three warnings:

- A Starlette deprecation warning about the current `httpx` integration.
- Two runtime warnings from mocked asynchronous WebSocket manager tests.
- A `Task was destroyed but it is pending!` message for the WebRTC session timeout worker during test teardown.

These warnings did not cause test failures. The pending timeout worker is a useful follow-up item because production-quality lifecycle cleanup should cancel all background workers deterministically.

---

## 12. Implemented Strengths

1. **Protocol separation:** Each communication mechanism has a distinct purpose and code path.
2. **Configurable node identity:** One backend image supports multiple logical nodes.
3. **Local evidence ownership:** Evidence storage is associated with its owning node.
4. **Typed contracts:** Pydantic schemas and generated protobuf code reduce ambiguous payload handling.
5. **Explicit failure paths:** Node, broker, peer, and WebRTC availability errors are surfaced.
6. **Idempotency:** RabbitMQ and P2P message processing include duplicate protection.
7. **Lifecycle management:** Startup and shutdown coordinate gRPC, RabbitMQ, P2P, and WebRTC resources.
8. **Reproducible demonstration:** Seed, reset, simulation, and deterministic media features support an FA-1 presentation.
9. **Broad automated coverage:** The suite covers both isolated components and distributed workflows.
10. **Operational visibility:** Health endpoints and system/messaging/peer pages expose runtime state.

---

## 13. Current Limitations and Boundaries

The following points are important when presenting the current implementation:

1. **The Unit 3 state is in memory.** Clock, election, lock, beacon, and snapshot state is not persisted to PostgreSQL.
2. **Unit 4 replication is a catalog demonstration.** It records replication metadata/events but does not implement a full binary transfer protocol.
3. **Demo media is synthetic.** The WebRTC tracks generate deterministic video/audio and are not connected to physical cameras.
4. **Only two evidence nodes are started by Compose.** Security and mobile roles are represented in code/demo data but require additional service instances for full runtime topology.
5. **Authentication and authorization are not implemented.** The current application is an educational local/demo deployment and should not be exposed directly to an untrusted network.
6. **RabbitMQ defaults are development credentials.** Production deployment requires secret management and non-default credentials.
7. **The frontend has six lint warnings.** They are non-blocking but should be removed before treating the UI as warning-clean.
8. **WebRTC test teardown has a pending-worker warning.** Session timeout worker cancellation can be tightened.
9. **The project depends on external runtime services.** A complete deployment requires PostgreSQL, RabbitMQ, Docker, and appropriate environment variables.
10. **Raw evidence remains node-local.** A remote evidence request returns metadata/remote results through RPC; it is not a centralized evidence archive.

---

## 14. Recommended Run Sequence

1. Copy [`.env.example`](.env.example) to `.env` and set a valid PostgreSQL `DATABASE_URL`.
2. Start the stack:

   ```powershell
   docker compose up --build
   ```

3. Open the frontend at `http://localhost:3000`.
4. Check backend health at `http://localhost:8000/health`.
5. Seed the scenario through the demo controls or:

   ```powershell
   .\.venv\Scripts\python.exe scripts\seed_demo.py
   ```

6. Walk through `/dashboard`, `/incidents/INC-000001`, `/messaging`, `/peers`, `/live`, and `/system`.
7. Use the demo controls to simulate node failure/recovery and observe the event stream.
8. For development validation:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest services\node\tests -q
   Set-Location frontend
   npm run lint
   npm run build
   ```

---

## 15. Final Assessment

The current worktree contains a substantial, functioning distributed-systems teaching implementation rather than only a static design. The core distributed communication paths, node registry, evidence/incident domain, event propagation, P2P mesh, WebRTC demo, Unit 3 algorithms, Unit 4 replication demonstration, frontend command center, Docker topology, migrations, and automated tests are all present.

The strongest evidence of implementation completeness is the combination of:

- 110 passing backend tests across the distributed features.
- A successful production frontend build and TypeScript validation.
- Explicit endpoint and protocol implementations in the backend.
- Separate node, broker, UI, and storage concerns in Docker Compose.
- Reproducible demo and reset controls.

The remaining work is primarily production hardening and polish: authentication, secret management, persistent Unit 3/Unit 4 state where required, additional compose nodes, cleanup of frontend lint warnings, and deterministic cancellation of WebRTC background workers.

