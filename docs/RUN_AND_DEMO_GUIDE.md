# EchoVault — Step-by-Step Run & Concept Walkthrough

This guide does two things:

1. **Runs the project** from a clean machine (Part A).
2. **Walks through every concept from Unit 1 to Unit 4** of the Distributed Systems syllabus, showing where each one lives in EchoVault, how to trigger it, and what to say about it (Part B).

Each step has a **Do** (what to click or type), a **See** (what should happen), and **Guide notes** (what the concept is and what to tell the examiner).

---

## Part A — Run the project

### A1. What you need

| Requirement | Why |
| :--- | :--- |
| Docker Desktop (running) | Runs RabbitMQ, the coordinator backend, two evidence nodes and the frontend |
| A PostgreSQL database | Stores nodes, evidence, incidents and messages. Use your Neon URL, or a local container (A3) |
| A browser (Chrome or Edge) | Opens the investigator dashboard |
| Optional: Python 3.11+ | Only needed to run the automated tests (Part C) |

### A2. What runs, and where

| Service | Address | Role |
| :--- | :--- | :--- |
| Frontend (Investigator dashboard) | http://localhost:3000 | Next.js command centre |
| Coordinator backend (FastAPI) | http://localhost:8000 (API docs at `/docs`) | Registry, incidents, REST APIs, WebSocket stream |
| Node A — CCTV-A | http://localhost:8001, gRPC `50051` | Evidence owner |
| Node B — CCTV-B | http://localhost:8002, gRPC `50052` | Evidence owner |
| RabbitMQ | AMQP `5672`, management UI http://localhost:15672 (guest / guest) | Asynchronous event bus |

### A3. Configure the database (`.env`)

The stack reads its settings from a file named `.env` in the project root. The template is `.env.example`.

**Do**

1. Copy the template:
   ```powershell
   cd C:\Users\Mayuresh\Desktop\echovault\EchoVault
   copy .env.example .env
   ```
2. Open `.env` and set `DATABASE_URL`.
   - **With Neon (normal setup):** paste your Neon URL, in the form `postgresql+asyncpg://user:password@host/database?sslmode=require`.
   - **With a local PostgreSQL container (no cloud account needed):**
     ```powershell
     docker run -d --name echovault-pg -e POSTGRES_USER=echovault -e POSTGRES_PASSWORD=echovault -e POSTGRES_DB=echovault -p 5432:5432 postgres:16-alpine
     ```
     Then set `DATABASE_URL=postgresql+asyncpg://echovault:echovault@echovault-pg:5432/echovault`.
     The name `echovault-pg` only resolves after step A4 attaches the container to the compose network (see A4, step 3).

> **Guide note:** `.env` is git-ignored on purpose. Credentials never go into the repository. The same image runs as every node; only the environment variables differ (`NODE_ID`, ports, node type). That is the "one codebase, many nodes" design you will explain in Unit 1.

### A4. Start the stack

**Do**

1. Make sure Docker Desktop is running (the whale icon is steady, not animated).
2. Build and start everything:
   ```powershell
   docker compose up --build -d
   ```
   The first build takes several minutes because it downloads base images.
3. **Only if you use the local PostgreSQL container:** attach it to the compose network and restart the backend once:
   ```powershell
   docker network connect echovault_default echovault-pg
   docker compose up -d
   ```
4. Seed the demo scenario (creates nodes, incident `INC-000001` and four evidence items):
   ```powershell
   curl.exe -X POST http://localhost:8000/api/v1/demo/seed
   ```

**See**

- `docker compose ps` lists `backend` as `healthy`, and `rabbitmq`, `frontend`, `node-a`, `node-b` as `Up`.
- The seed call returns `"status":"success"`.

> **Guide note:** The backend's container command runs `alembic upgrade head` before starting the server. That means the database tables are created automatically. Alembic is a schema-migration tool: each file in `services/node/alembic/versions/` is one versioned change to the schema, so every node and every developer ends up with the same tables.

### A5. Verify every service is alive

**Do** — run these one by one:

```powershell
curl.exe http://localhost:8000/health
curl.exe http://localhost:8000/health/database
curl.exe http://localhost:8000/health/messaging
curl.exe http://localhost:8001/health
curl.exe http://localhost:8002/health
```

Then open http://localhost:3000/dashboard in your browser.

**See** — every health call returns JSON with `"status"` set to a healthy value. The dashboard shows the four-stage investigation flow and live metrics.

> **Guide note:** `/health` checks the process, `/health/database` checks the database, and `/health/messaging` checks RabbitMQ. Separating the checks is itself a distributed-systems point: a node can be alive while one of its dependencies is down, and the system should say which one.

### A6. Stop and restart

```powershell
docker compose down          # stop containers, keep data
docker compose up -d         # start again (no rebuild)
docker rm -f echovault-pg    # only if you used the local database container
```

---

## Part B — Concept walkthrough (Unit 1 → Unit 4)

Work through these in order. Each concept has its own demo steps. The total time is about 45 minutes for a full walkthrough; the 15-minute version is marked **[Quick]**.

---

### UNIT 1 — Introduction to Distributed Systems

#### 1.1 What a distributed system is: autonomous nodes

**Theory:** A set of independent computers that communicate only by messages and appear to the user as one system.

**Where:** Four evidence nodes (`CCTV-A`, `CCTV-B`, `SECURITY-A`, `MOBILE-A`) plus the coordinator backend. Each is its own process with its own address.

**Do**

1. Open http://localhost:3000/nodes.
2. Look at the registry table.

**See** — each node has a `node_id`, a type, a host and port, and a gRPC port.

> **Guide note:** "Each node is autonomous. It owns its evidence, runs its own server, and keeps working if another node stops. The registry is only a directory of who exists and where to reach them." Point to the two port columns and say that the same codebase was started four times with different environment variables.

Check it from the API:
```powershell
curl.exe http://localhost:8001/api/v1/node/self
```

#### 1.2 Goals: resource sharing, openness, scalability, fault isolation

**Theory:** The four goals of a distributed system.

**Where and how to show each:**

| Goal | Show it | Say |
| :--- | :--- | :--- |
| Resource sharing | Incident page → **Fetch via gRPC** on `EV-002` | "CCTV-B's evidence is read by the coordinator without copying the file." |
| Openness | `/docs` on port 8000 | "Every service is described by open standards: HTTP/JSON, Protobuf, AMQP, WebSocket, WebRTC." |
| Scalability | `curl.exe http://localhost:8000/api/v1/nodes` lists the registry | "A new node joins by registering with `POST /api/v1/nodes`. No coordinator code changes." |
| Fault isolation | System page → **Simulate Crash (Offline)** on `CCTV-B` | "CCTV-A, RabbitMQ and the dashboard keep working." |

#### 1.3 Types of distributed systems

**Theory:** Information systems, multimedia systems and peer-to-peer systems.

**Where:**

- **Distributed information system:** `/incidents/INC-000001` joins evidence from four owners into one case.
- **Distributed multimedia system:** `/live` streams live video from a node.
- **Peer-to-peer system:** `/peers` sends messages directly between nodes.

> **Guide note:** Say which type each screen belongs to. A real system is often a mix of all three.

#### 1.4 Architecture and middleware

**Theory:** Architecture describes how components are arranged. Middleware is the software layer that lets components talk.

**Where:** EchoVault uses a *hybrid* architecture: nodes own their data (decentralised), a coordinator provides the registry and dashboard (centralised), and a message bus connects them (publish/subscribe).

**Do:** Open http://localhost:3000/dashboard and scroll to the **Distributed scene map**. Point to the RabbitMQ bus in the middle.

**Middleware used:**

| Middleware | Used for |
| :--- | :--- |
| gRPC | Synchronous remote calls between nodes |
| RabbitMQ | Asynchronous events |
| WebSocket | Live pushes to the browser and direct node-to-node links |
| WebRTC | Live audio and video |

> **Guide note:** "Each protocol is chosen for one job. Forcing everything through one protocol would make some jobs slow or unreliable." The comparison table in `README.md` (section 2) lists all six mechanisms.

#### 1.5 Virtualisation and containerisation

**Theory:** Packaging each component with its runtime so it runs the same everywhere.

**Where:** `docker-compose.yml` defines six containers: RabbitMQ, backend, two nodes, frontend.

**Do:**
```powershell
docker compose ps
```

**See** — six services, each in its own container, each with its own ports.

> **Guide note:** "Docker gives isolation: each node has its own file system and network namespace. It is not a virtual machine, so it starts in seconds."

#### 1.6 Model of distributed computation: no shared memory

**Theory:** Processes have private memory and communicate only through messages.

**Where:** Node A never reads Node B's database or files. The only way to get B's evidence is a message (gRPC, Part 2.2 below).

> **Guide note:** Ask the examiner: "How does CCTV-A see CCTV-B's evidence?" Answer: "It sends a `GetEvidence` request over gRPC and gets a reply message. There is no shared variable or shared table."

---

### UNIT 2 — Communication in Distributed Systems

#### 2.1 Layered protocols

**Theory:** Communication is split into layers. The transport layer delivers bytes; the application layer defines their meaning.

**Where:** The stack from bottom to top for one gRPC call is TCP → HTTP/2 → Protobuf message → the `NodeService` method.

> **Guide note:** Name the layers for one request. This shows you understand the layering, not just the library names.

#### 2.2 Remote Procedure Call (RPC) — gRPC  **[Quick]**

**Theory:** Calling a function on another machine as if it were local. The client calls a *stub*; the server runs a *skeleton* method; the arguments travel as binary messages.

**Where:** `proto/echovault/node.proto` defines the `NodeService` contract:

| Method | Purpose |
| :--- | :--- |
| `GetNodeInfo` | Identity of the node |
| `GetNodeStatus` | Health of the node |
| `GetEvidence` | Metadata for one evidence item |
| `GetEvidenceByIncident` | All evidence for an incident |
| `Ping` | Liveness check |

**Do**

1. Open http://localhost:3000/incidents/INC-000001.
2. Click **Fetch via gRPC** next to `EV-002` (owned by `CCTV-B`).

**Or from the terminal:**
```powershell
curl.exe http://localhost:8000/api/v1/remote/nodes/CCTV-B/status
curl.exe http://localhost:8000/api/v1/remote/nodes/CCTV-B/evidence/EV-002
```

**See** — the response includes metadata and a measured latency in milliseconds.

> **Guide note:** Points to make:
> - **Typed contract:** the `.proto` file is the single source of truth for both sides.
> - **Binary, HTTP/2:** smaller and faster than JSON, with multiplexed calls.
> - **Timeouts:** every call has a deadline (`GRPC_TIMEOUT_SECONDS=5`). A dead node cannot block the dashboard forever.
> - **Error codes:** an unreachable node returns `UNAVAILABLE`; an unknown evidence ID returns `NOT_FOUND`.
>
> Ask yourself the examiner's question: "What happens if CCTV-B is offline?" Show it: stop CCTV-B and click **Fetch via gRPC** again. The request fails within the timeout, and the rest of the page still works.

#### 2.3 Message-oriented communication — RabbitMQ  **[Quick]**

**Theory:** The sender publishes a message to a named exchange and does not wait. Consumers receive it later. Publisher and consumer never talk directly.

**Where:** Exchange `echovault.events` (topic). Each node has its own durable queue `echovault.node.{NODE_ID}`, bound to the topics it cares about. Failed messages go to the dead-letter exchange `echovault.dead-letter`.

**Do**

1. Open http://localhost:15672 (guest / guest). Go to **Exchanges** → `echovault.events`.
2. Open http://localhost:3000/messaging and click **Publish test event**.

**See** — the event appears in the live feed on `/messaging`, and in the RabbitMQ queues with a message count.

> **Guide note:** Cover these concepts:
> - **Decoupling:** the publisher does not know who consumes the event.
> - **Topic routing:** routing keys such as `evidence.created` and `node.status_changed` select which queues receive the message.
> - **Persistence:** messages are published with `delivery_mode=2`, so they survive a broker restart. Queues are durable.
> - **Acknowledgements:** a consumer confirms each message after it processes it, so a crash before the ack causes redelivery.
> - **Retry and dead-letter:** after `RABBITMQ_RETRY_LIMIT` (3) failed deliveries, the message moves to the dead-letter exchange instead of looping forever.
> - **Idempotency:** consumers store received message IDs, so a redelivered message is not processed twice.

#### 2.4 Stream-oriented communication — WebSocket  **[Quick]**

**Theory:** One connection stays open; the server pushes events as they happen. The browser never polls.

**Where:** `ws://localhost:8000/ws/events`. Each client can attach filters on the server (event type, node, incident).

**Do**

1. Open http://localhost:3000/messaging and leave the filters empty (all events).
2. Click **Publish test event →**.

**See** — the event appears in the live feed with no page refresh.

> **Guide note:** "The server pushes the event over the open WebSocket. The browser never asks for it."
>
> ⚠ Don't subscribe to `INC-000001` before publishing the test event. The test event has no incident ID, so an incident filter drops it. Filters match only events that carry that ID.

#### 2.5 Peer-to-peer direct communication — P2P WebSocket  **[Quick]**

**Theory:** Two nodes talk directly, with no broker in the path. Before any message flows, the two sides run a *handshake* to confirm each other's identity.

**Where:** The P2P console at http://localhost:3000/peers. Underneath, nodes use the `/ws/peer` WebSocket. Messages are `HANDSHAKE` / `HANDSHAKE_ACK`, `PING` / `PONG`, `PEER_MESSAGE`, `EVIDENCE_ANNOUNCEMENT` and `INCIDENT_ANNOUNCEMENT`.

**Do** — four steps, one per panel:

1. **Select a node.** In **1 · Select a node**, choose `CCTV-B`. The card shows its address (`node-b:8002`) and link state.
2. **Connect.** Click **Connect**. The link badge turns green (`CONNECTED`). This is the handshake.
3. **Act.** In **2 · Choose an action**:
   - **Ping**: the result shows the round-trip time in milliseconds.
   - **Send**: type a message and send it.
   - **Announce**: pick an evidence item, or an incident, and announce it.
   Every action opens the link automatically if it is closed, so you can skip step 2.
4. **Check the inbox.** The **Inbox — messages received** table lists the messages. Click **Refresh** if needed. The **Session log** shows each action with its outcome.

**Try a failure on purpose.** Select `MOBILE-A` and click **Connect**. The result says `Connection refused`. The node isn't running in this stack, and the rest of the console keeps working. This is the fault-isolation point of Unit 2.

**See** — Ping shows a green latency number. Send shows a delivery confirmation. The inbox gains a row for each message.

> **Guide notes:**
> - **Handshake:** the first message on a new connection must be `HANDSHAKE`. The server rejects any connection that doesn't start that way, so both sides confirm each other's identity before anything else flows.
> - **Round trip:** `PING` carries a timestamp, and `PONG` echoes it back. The sender subtracts to get the round-trip time. That is the number on the Ping result.
> - **No broker:** messages go node to node over `/ws/peer`. Stop RabbitMQ and the P2P console still works. That is the difference from the RabbitMQ path in section 2.3.
> - **Idempotency:** each message has its own ID, and the receiver stores IDs it has already seen, so a duplicate delivery is ignored.
> - **Heartbeats are hidden from the inbox.** `PING` and `PONG` are still stored in the database. The inbox shows only business messages.
> - **Shared database caveat:** all nodes in this demo share one database, so the inbox shows messages that were both sent and received. Say this if the examiner asks why the coordinator's inbox has messages from CCTV-B.

#### 2.6 WebRTC — live multimedia  **[Quick]**

**Theory:** Real-time audio and video between two peers. Signalling (setting up the call) is separate from media (the actual RTP/SRTP streams). Signalling needs a server; the media goes peer to peer.

**Where:** Signalling on `ws://localhost:8000/ws/webrtc/{session_id}`. Sessions are created at `POST /api/v1/webrtc/sessions`.

**Do**

1. Open http://localhost:3000/live. Choose `CCTV-A` and click **Start Live WebRTC Session**.
2. Watch the video stage, the timestamp overlay and the session status.
3. Check the session record:
   ```powershell
   curl.exe http://localhost:8000/api/v1/webrtc/sessions
   ```

**See** — a live 25 FPS video stream. The session appears in the list with a status.

> **Guide note:**
> - **SDP Offer / Answer:** the browser sends an offer describing what it can receive; the node answers.
> - **ICE candidates:** each side lists possible network paths; they are exchanged ("trickled") until a working path is found.
> - **Timeout:** if the session is not connected within `WEBRTC_SESSION_TIMEOUT_SECONDS` (45 s), it is marked FAILED instead of hanging.
> - **Demo media:** the video is generated by the node, not a physical camera. Say so honestly: this is for reproducible testing.

#### 2.7 Names, identifiers and addresses

**Theory:** A *name* identifies a thing; an *address* says where to reach it. Keep them separate so a thing can move without changing its name.

**Where:**

- Logical names: `node_id` (`CCTV-A`), `incident_id` (`INC-000001`), `evidence_id` (`EV-002`).
- Addresses: `host:port`, `grpc_host:grpc_port`, `p2p_host:p2p_port`.

**Do:** `curl.exe http://localhost:8000/api/v1/nodes` and compare the `node_id` fields with the host and port fields.

> **Guide note:** "EV-002 is still called EV-002 even if CCTV-B moves to another machine. Only the address changes, and the registry records it."

#### 2.8 Reliability and fault tolerance

**Theory:** Detect failures, limit their damage, and recover.

**Where and how to show it:**

| Mechanism | Show it | Say |
| :--- | :--- | :--- |
| Heartbeat liveness | `curl.exe -X POST http://localhost:8000/api/v1/nodes/CCTV-B/heartbeat` | "A node that stops sending heartbeats is marked stale." |
| Fault injection | System page → **Simulate Crash (Offline)** on `CCTV-B`, then **Recover Node (Online)** | "The system survives the crash and recovers when the node returns." |
| Timeouts | Fetch via gRPC while CCTV-B is offline | "Requests fail fast, not forever." |
| Dead-letter queues | RabbitMQ management UI → dead-letter exchange | "Bad messages are parked for inspection." |
| Duplicate detection | Send the same P2P message twice | "The second copy is recognised and ignored." |

---

### UNIT 3 — Synchronisation

The Unit 3 coordination lab is the **Coordination Lab** section of **http://localhost:3000/system**. Every algorithm below has its own button. You never need Swagger for these.

First, open http://localhost:3000/system and click **Reset Unit 3 State** so you start from known values.

#### 3.1 Logical clocks — Lamport's algorithm  **[Quick]**

**Theory:** Wall-clock time can drift between machines, so it cannot order events reliably. Lamport clocks use a counter instead:
- A local event increments the counter.
- A received message carries the sender's counter; the receiver sets `counter = max(local, received) + 1`.

**Do**

1. In **Lamport Logical Clock**, choose `CCTV-A` and click **Tick Lamport Clock**. Note the value.
2. Type `8` in **Received timestamp** and click **Tick Lamport Clock** again.

**See** — the first tick gives the next number. With `8` received, the clock jumps to `max(local, 8) + 1`.

> **Guide note:** "Lamport clocks give a *happened-before* order: if event A could have caused event B, A's clock value is smaller. They do not tell you the exact time, only the order."

#### 3.2 Beacon protocol (heartbeat)

**Theory:** A node periodically sends a beacon. The receiver knows the node is alive and can use the beacon to advance its clock.

**Do:** In the **Topology, Priorities & Node Failure** table, click **Send Beacon** for `CCTV-B`.

**See** — the "Last beacon" column shows a time, and the node's Lamport clock increases.

> **Guide note:** "A beacon both proves liveness and carries logical time. A silent node is suspected failed."

#### 3.3 Clock synchronisation — Cristian's algorithm

**Theory:** A client asks a time server for the time. It measures the round-trip time (RTT) and assumes the reply was sent halfway through. Offset = server time − (local time − RTT/2).

**Do:** In **Cristian Clock Synchronization**, choose `CCTV-B` and click **Synchronize Clock**.

**See** — a result line with the offset in milliseconds and the measured round trip.

> **Guide note:** "The assumption is that the delay is symmetric. The error is at most half the RTT, which is why Cristian's method suits networks with stable latency." In this demo all clocks run on one machine, so the offset is close to zero. Say this openly; it is a demonstration of the calculation, not of real clock drift.

#### 3.4 Election — Bully algorithm

**Theory:** When the coordinator fails, the live node with the highest priority wins. Each node has a fixed priority.

**Priorities:** `SECURITY-A` = 4, `CCTV-A` = 3, `CCTV-B` = 2, `MOBILE-A` = 1.

**Do**

1. In **Bully Leader Election**, click **Run Election**. The leader is `SECURITY-A` (highest priority, online).
2. Click **Fail Current Leader**. `SECURITY-A` goes OFFLINE and the next highest, `CCTV-A`, becomes leader.
3. In the node table, click **Send Beacon** on `SECURITY-A` to bring it back, then **Run Election** again.

**See** — the leader changes as nodes fail and recover.

> **Guide note:** "Bully is simple: the highest-priority live process wins. Its weakness is that it needs a stable priority order and can send many messages during an election." Mention that the election is triggered by *detecting* the failure; here the failure is simulated by the button.

#### 3.5 Mutual exclusion — coordinator-based lock with FIFO queue

**Theory:** Only one process may use a shared resource at a time. A coordinator grants the lock; others wait in a queue.

**Do**

1. Leave the resource as `INC-000001`. Choose `CCTV-A` and click **Request Lock**. It is granted.
2. Choose `CCTV-B` and click **Request Lock**. It is queued behind `CCTV-A`.
3. Choose `CCTV-B` and click **Release Lock**. Nothing happens, because only the owner can release. The message says so.
4. Choose `CCTV-A` and click **Release Lock**. `CCTV-B` is promoted automatically.

**See** — the owner and queue fields update on every step. A failed request shows the reason, for example `Only the lock owner can release the lock`.

> **Guide note:** "Only one node enters the incident-finalisation section at a time. The queue is first-in, first-out, so nobody starves. The coordinator is a single point of coordination, which is the trade-off of this design."

#### 3.6 Global snapshots — marker-based

**Theory:** Record the state of every process and of the messages in transit so the recording is consistent. A marker message travels the channels to trigger each process to record its state.

**Do:** Click **Capture Global Snapshot**.

**See** — a snapshot ID, the leader, the Lamport clock, the lock owner, and the number of nodes recorded.

> **Guide note:** "The snapshot is one consistent picture of the whole system at one logical moment. It is used for debugging and for detecting deadlock or lost messages." Be honest: this demo captures node state; it does not model messages in transit.

#### 3.7 Validation and error behaviour

**Do:**

1. In **Coordinator-Based Mutual Exclusion**, clear the **Resource ID** and click **Request Lock**. The message is a 422 validation error: `resource_id: String should have at least 1 character`.
2. Click **Fail Node & Re-elect** on a node that is already OFFLINE: the button is disabled. Sending a lock request for an OFFLINE node via the API returns `Requesting node is not online` (HTTP 409).

> **Guide note:** Distinguish the two codes: **422** means the request is malformed; **409** means the request is valid but conflicts with the current state.

---

### UNIT 4 — Emerging Distributed Paradigms

Unit 4 is on the **Evidence Replication Catalog** section of **http://localhost:3000/system**.

First click **Reset Replication Catalog** so the catalog starts empty.

#### 4.1 Distributed object-based and web-based systems

**Theory:** Objects (with methods) distributed over the network, and web systems where the browser is a client of remote services.

**Where:** The gRPC `NodeService` is a remote object: its methods are called from another machine (Part 2.2). The System console is a web client that calls REST and WebSocket APIs.

> **Guide note:** "The browser does not contain any evidence. It is a client of distributed services, and it can be on any machine."

#### 4.2 Distributed file-system concepts — replication catalog  **[Quick]**

**Theory:** A distributed file system keeps copies of files on several machines so data survives a failure. Each copy has an owner, a location, and a checksum to prove it is unchanged.

**Where:** The replication catalog records, for each evidence item: owner node, replica node, file name, file size, checksum, status, and an ID with a timestamp.

**Do**

1. In **Request Evidence Replication**, keep the defaults (`EV-DEMO-001`, owner `CCTV-A`, target `CCTV-B`) and click **Replicate Evidence**.
2. Read the result: a replication ID (`REPL-…`), the target, and a checksum marked *automatic SHA-256*.
3. In **Replica Lookup**, enter `EV-DEMO-001` and click **Look Up Replica**.
4. Enter `EV-NOPE` and click **Look Up Replica** again. The message is `Evidence has no replica`.
5. Set the target to the same node as the owner and click **Replicate Evidence**. The error is `Replica target must differ from the owner`.

**See** — each step shows a success or a specific error in the panel.

> **Guide note:**
> - **Owner vs replica:** the owner is the node that captured the evidence; the replica is the copy's location.
> - **Checksum:** a SHA-256 fingerprint. If a copy's checksum differs from the original, the copy is corrupt.
> - **Important honest limit:** this is a **metadata and event demonstration**. The physical evidence file is *not* copied between nodes yet. The automatic checksum is the SHA-256 of the evidence ID, not of file bytes, because no file is transferred. Say this before the examiner asks.

#### 4.3 Serverless architecture — event-triggered function  **[Quick]**

**Theory:** Code runs only when an event triggers it, with no server to manage. A stateless function receives the event, does its work, and emits a result event.

**Where:** The `replication_worker` function handles each replication request and emits a `replication.completed` event. The event appears in the **Event-Driven Replication Events** table.

**Do:** After step 4.2.1, read the new row in the events table: event `replication.completed`, function `replication_worker`, evidence `EV-DEMO-001`, status `completed`.

> **Guide note:** "The worker holds no state between requests. The catalog stores the result, and the event announces that the work is finished, so other components can react without polling."

Also explain the second function listed in the panel, `fallback_retrieval`: it is the retrieval role, and the **Replica Lookup** is its entry point. Be precise: it has no separate code path of its own.

#### 4.4 Case studies and self-study (discussion topics)

These are for discussion, not for running:

| Topic | Link to EchoVault |
| :--- | :--- |
| Edge and serverless platforms (Cloudflare, AWS Lambda) | The replication worker is the same idea: a function triggered by an event |
| Hadoop / HDFS | Replication with a catalog of locations, as in 4.2 |
| Kubernetes vs Docker Compose | Compose runs the same six containers on one machine; Kubernetes would schedule them across many |
| Blockchain and distributed databases | Trade-offs of consensus and immutability; EchoVault uses neither, by design |

---

## Part C — Automated tests (proof that the code works)

Run the backend test suite:

```powershell
cd services\node
python -m pytest tests -q
```

**Expected result:** `110 passed, 1 skipped`. The skipped test needs a live external database.

What the tests cover, grouped by concept:

| Concept | Test files |
| :--- | :--- |
| Unit 1 — nodes, evidence, incidents | `test_api.py`, `test_incident_rules.py` |
| Unit 2 — gRPC | `test_grpc_contract.py` |
| Unit 2 — RabbitMQ | `test_messaging_*.py` |
| Unit 2 — WebSocket | `test_websocket_*.py` |
| Unit 2 — P2P | `test_p2p_*.py` |
| Unit 2 — WebRTC | `test_webrtc_*.py` |
| End-to-end and two-node integration | `test_e2e_distributed_workflow.py`, `test_integration_two_nodes.py` |
| Unit 3 — clocks, election, lock | `test_unit3.py` |
| Unit 4 — replication catalog | `test_unit4.py` |

---

## Part D — Recommended presentation order (about 15 minutes)

1. **Start** — http://localhost:3000/dashboard (Unit 1: architecture).
2. **Nodes** — http://localhost:3000/nodes (Unit 1: autonomous nodes, addressing).
3. **Incident and gRPC** — `/incidents/INC-000001`, click **Fetch via gRPC** (Unit 2: RPC).
4. **P2P** — `/peers`, ping and send an alert (Unit 2: direct messaging, handshake).
5. **Messaging** — `/messaging`, publish a test event (Unit 2: RabbitMQ, WebSocket).
6. **Live** — `/live`, start a WebRTC session (Unit 2: multimedia).
7. **System, fault** — `/system`, crash `CCTV-B`, then recover it (Unit 1 & 2: fault isolation).
8. **Unit 3** — in the Coordination Lab: tick clocks, sync, fail the leader, lock and queue, snapshot.
9. **Unit 4** — in the Replication Catalog: replicate, look up, see the event.
10. **Close** — state the limitations (Part E).

---

## Part E — Troubleshooting

| Symptom | Cause | Fix |
| :--- | :--- | :--- |
| `docker` is not recognised | Docker Desktop's CLI folder is not on PATH | Use the full path from Docker Desktop's install folder, or reopen the terminal after installing |
| Backend exits with `password authentication failed` | Wrong credentials, or another PostgreSQL on port 5432 answered | Check `DATABASE_URL` in `.env`; for the local container, use the container name `echovault-pg` and attach it to the compose network |
| Dashboard says "Failed to fetch" | Backend not running, or a database call failed | `docker compose ps`, then `docker compose logs backend` |
| Node list is empty | Seed not run | `curl.exe -X POST http://localhost:8000/api/v1/demo/seed` |
| Six nodes appear instead of four (`node-dev-001`, `node-docker-001` are extra) | The seed (`services/node/app/services/demo_seeder.py`, `DEMO_NODES`) includes these two coordinator entries. The seed response's `"nodes"` count only includes rows created in that run | Expected with the current seeder. Note that **Clean DB & Re-Seed** re-adds them too |
| RabbitMQ shows "checking…" or unhealthy | Broker still starting | Wait 30 seconds; check `docker compose logs rabbitmq` |
| WebRTC never connects | Browser or network blocks the ICE path | Use Chrome; try another node; the session fails cleanly after 45 s |

---

## Part F — Limitations to state openly

Stating these first earns more credit than being asked:

- **Demo media:** video and audio come from a generator, not a physical camera.
- **Replication is metadata only:** evidence files are not copied between nodes yet; the checksum is over the evidence ID.
- **Clock demo:** all clocks are on one machine, so Cristian offsets are close to zero.
- **Single coordinator:** the lock and election are coordinated by one backend; a coordinator failure is not handled by a second election.
- **No authentication:** the APIs are open, which is acceptable only for a local demonstration.
- **Snapshots:** the marker-based snapshot records node state, not messages in transit.
