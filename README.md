# EchoVault

EchoVault is a Distributed Digital Evidence Collection and Incident Reconstruction System. It is being developed as a Distributed Systems mini-project, with independent evidence-producing nodes and a coordinator boundary designed for incremental communication features.

> **Current implementation:** Part 4 adds incident management and local incident/evidence context. Evidence remains owned by its originating node; distributed communication features will be implemented incrementally.

## Architecture

```mermaid
flowchart LR
    Browser[Next.js frontend] -->|HTTP| Node[FastAPI node service]
    Node -->|TLS / async SQLAlchemy| Neon[(Neon PostgreSQL)]
    Proto[Versioned protocol definitions] -. future gRPC / messaging .-> Node
```

The frontend and backend are independently deployable. The node service receives its identity from configuration, allowing later instances such as Node A, Node B, and Node C without a monolithic shared process.

## Technology stack

- **Frontend:** Next.js, React, TypeScript, App Router
- **Backend:** Python, FastAPI, Pydantic
- **Database:** Neon PostgreSQL, SQLAlchemy async engine, asyncpg
- **Infrastructure:** Docker and Docker Compose
- **Version control:** Git

Part 1 and 2 intentionally do not add RabbitMQ, Redis, Kafka, local PostgreSQL, gRPC, WebSockets, WebRTC, P2P, or evidence/incident features.

## Environment setup

Copy `.env.example` to `.env`, then replace `DATABASE_URL` with your Neon connection string. It must use the async SQLAlchemy scheme and SSL:

`postgresql+asyncpg://username:password@host/database?sslmode=require`

No credentials belong in Git. The remaining variables configure the service and development node identity; sensible defaults are provided by the backend.

## Running locally

Install frontend dependencies with `npm install` from `frontend/`. Install backend dependencies in a Python virtual environment from `services/node/requirements.txt`.

Start the backend from the repository root with Uvicorn on port `8000`, and start the frontend with `npm run dev` from `frontend/` on port `3000`.

Backend endpoints:

- `GET /` — service status
- `GET /health` — application health
- `GET /health/database` — real Neon `SELECT 1` connectivity check; returns HTTP 503 on failure
- `GET /api/v1/node/self` — this process's configured identity and address
- `POST /api/v1/node/self/register` — idempotently register this process
- `POST /api/v1/nodes` — register a node
- `GET /api/v1/nodes` — discover nodes, optionally filtered by `node_type` or `status`
- `GET /api/v1/nodes/{node_id}` — retrieve node metadata
- `PATCH /api/v1/nodes/{node_id}` — update metadata or status
- `POST /api/v1/nodes/{node_id}/heartbeat` — set a node `ONLINE` and update `last_seen_at`
- `DELETE /api/v1/nodes/{node_id}` — soft-deactivate a node as `OFFLINE`
- `POST /api/v1/evidence` — create an observation owned by the configured node
- `GET /api/v1/evidence` — list only this node's non-deleted evidence
- `GET /api/v1/evidence/{evidence_id}` — retrieve local evidence metadata
- `PATCH /api/v1/evidence/{evidence_id}` — update local metadata
- `DELETE /api/v1/evidence/{evidence_id}` — soft-delete local evidence
- `POST /api/v1/evidence/upload` — upload an allowed file to node-owned storage
- `GET /api/v1/evidence/{evidence_id}/file` — download a local evidence file
- `POST /api/v1/incidents` — create an incident owned by the configured node
- `GET /api/v1/incidents` — list incidents with status/type/severity filters
- `GET /api/v1/incidents/{incident_id}` — retrieve incident metadata
- `PATCH /api/v1/incidents/{incident_id}` — update incident status and metadata
- `POST /api/v1/incidents/{incident_id}/evidence/{evidence_id}` — attach local evidence
- `DELETE /api/v1/incidents/{incident_id}/evidence/{evidence_id}` — remove an association only
- `GET /api/v1/incidents/{incident_id}/evidence` — list evidence known locally
- `POST /api/v1/incidents/{incident_id}/nodes/{node_id}` — add a participating node
- `GET /api/v1/incidents/{incident_id}/nodes` — list participating nodes
- `DELETE /api/v1/incidents/{incident_id}/nodes/{node_id}` — mark a node inactive
- `GET /api/v1/remote/nodes/{node_id}/status` — retrieve status through gRPC
- `GET /api/v1/remote/nodes/{node_id}/evidence/{evidence_id}` — retrieve remote metadata through gRPC
- `GET /api/v1/remote/nodes/{node_id}/incidents/{incident_id}/evidence` — retrieve remote incident evidence through gRPC

The registry distinguishes **identity** (`node_id`), **address** (`host` + `port`), and **state** (`status` + `last_seen_at`).

## Remote Procedure Call

Part 5 adds gRPC as internal communication middleware between independent nodes. The caller never accesses a peer's database directly:

```text
Application logic → gRPC middleware → network → remote NodeService → remote database
```

The protobuf contract is `proto/echovault/node.proto`; generated Python stubs live under `services/node/app/grpc/generated/`. Supported methods are `Ping`, `GetNodeInfo`, `GetNodeStatus`, `GetEvidence`, and `GetEvidenceByIncident`. Evidence RPCs expose metadata only, never filesystem paths or file contents.

Every outbound RPC uses the target node's registered `grpc_host` and `grpc_port`, carries a request ID, and has a configurable deadline through `GRPC_TIMEOUT_SECONDS`. Remote failures are returned as HTTP 503 and missing remote evidence as HTTP 404.

Run the HTTP and gRPC ports separately. For local two-node development, configure `CCTV-A` as HTTP `8001`/gRPC `50051` and `CCTV-B` as HTTP `8002`/gRPC `50052`, register both nodes with `/api/v1/node/self/register`, then call the remote endpoints from either node. Compose includes `node-a` and `node-b` with the same image and separate identities.

## Incident model

An incident is a shared logical context, not an evidence owner:

```text
Incident INC-001
├── Evidence from Node A (owned by Node A)
├── Evidence from Node B (owned by Node B)
└── Evidence from Node C (owned by Node C)
```

At this stage, an incident node can access only evidence known to the local node. Distributed evidence aggregation will be introduced through RPC and message-oriented communication in subsequent parts. Incident statuses follow `OPEN → INVESTIGATING → RESOLVED → CLOSED`; `OPEN → CLOSED` is also allowed.

## Evidence Node Architecture

Each running process owns the evidence it creates. The server assigns ownership from `NODE_ID`; a client cannot submit or override `node_id`.

```text
Node A (CCTV-A) → owns evidence created by CCTV-A
Node B (CCTV-B) → owns evidence created by CCTV-B
Node C (MOBILE-A) → owns evidence created by MOBILE-A
```

Evidence metadata is stored in Neon with a foreign key to the node registry. Files are stored outside PostgreSQL under `storage/evidence/<NODE_ID>/` and are never served through arbitrary filesystem paths. `captured_at` is when the observation happened, `received_at` is when this node recorded it, and `created_at` is the database record creation time.

For two local instances, use the same code and database with separate environment values:

```text
NODE_ID=CCTV-A  NODE_NAME="CCTV Camera A"  NODE_TYPE=EVIDENCE  NODE_HOST=localhost  PORT=8001
NODE_ID=CCTV-B  NODE_NAME="CCTV Camera B"  NODE_TYPE=EVIDENCE  NODE_HOST=localhost  PORT=8002
```

Run the migration first, register each configured node with `POST /api/v1/node/self/register`, and each instance's evidence list remains node-local.

## Database migration and seed data

Run the Alembic migration after configuring Neon:

`python -m alembic upgrade head`

Then optionally add `CCTV-A`, `CCTV-B`, and `SECURITY-A` safely:

`python scripts/seed_nodes.py`

The seed script is idempotent. The migration, not application startup, owns database schema creation.

## Docker

After configuring `.env`, run `docker compose up --build`. The frontend is available at `http://localhost:3000` and the backend at `http://localhost:8000`. Stop the stack with `docker compose down`. Compose contains only `frontend` and `backend`; Neon remains an external managed database.

Convenience targets include `make install`, `make frontend`, `make backend`, `make build`, `make up`, `make down`, and `make logs`.

## Future development

Later parts will add, in sequence:

1. Node identity and registry
2. Evidence node service
3. Incident management
4. gRPC
5. RabbitMQ
6. WebSockets
7. P2P communication
8. WebRTC
9. Incident reconstruction
10. Dashboard
11. Integration/testing

These features are intentionally outside Part 1.
