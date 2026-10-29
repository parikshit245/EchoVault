# EchoVault — FA-1 Viva & Oral Examination Guide

Comprehensive questions and model answers for the Distributed Systems FA-1 evaluation.

---

### Q1: Why is EchoVault a Distributed System rather than a monolithic web application?
**Answer**: EchoVault consists of autonomous evidence nodes running as independent operating processes on separate network addresses (ports 8000, 8001, 8002, 8003). Each node maintains its own local memory, local evidence storage, and execution state. They coordinate strictly via network communication (gRPC, RabbitMQ, P2P WebSockets, and WebRTC) without shared global memory.

---

### Q2: Why shouldn't all evidence nodes directly connect to the same central database for raw file storage?
**Answer**:
1. **Single Point of Failure (SPOF)**: A central DB failure halts evidence collection across all facilities.
2. **Bandwidth Bottlenecks**: Large multimedia files (CCTV video streams) would saturate central network links.
3. **Data Ownership & Jurisdiction**: Evidence nodes represent physical facilities (e.g. airport vs bank) that require local data sovereignty. Remote nodes should query metadata through strict RPC interfaces rather than unrestricted SQL access.

---

### Q3: What is the difference between RPC (gRPC) and Message-Oriented Communication (RabbitMQ)?
**Answer**:
- **gRPC (RPC)**: Synchronous, 1-to-1, tightly coupled communication. The caller sends a request and blocks until a response is returned or a deadline expires. Used when immediate data is required (e.g. `GetEvidence`).
- **RabbitMQ (MOM)**: Asynchronous, 1-to-N, temporally decoupled communication. The publisher emits an event and continues immediately. Messages are buffered in queues and delivered even if consumers are temporarily offline.

---

### Q4: Why use WebSockets for real-time dashboard events instead of HTTP polling?
**Answer**: HTTP polling introduces latency (proportional to the poll interval) and high request overhead (headers, TCP/TLS handshake re-establishment). WebSockets maintain a persistent, lightweight, full-duplex TCP connection that enables the server to push events with sub-millisecond overhead.

---

### Q5: Why is WebSocket not the same as WebRTC? Why do we need WebRTC for multimedia?
**Answer**:
- **WebSocket**: Runs over TCP. TCP enforces reliable, in-order delivery via retransmission. In live video streaming, retransmitting dropped video frames introduces head-of-line blocking and cumulative buffering latency.
- **WebRTC**: Runs over UDP using SRTP (Secure Real-Time Transport Protocol). It prioritizes timeliness over complete reliability, delivering real-time 25 FPS video without buffering lag. WebSocket is used only for WebRTC *signaling* (negotiating SDP/ICE).

---

### Q6: Why implement Direct P2P messaging if RabbitMQ already exists?
**Answer**:
1. **Broker Independence**: Direct P2P channels (`/ws/peer`) allow critical node-to-node communication to continue even if the RabbitMQ message broker fails or is partitioned.
2. **Direct Control & Low Latency**: Bypasses queue scheduling and broker serialization for high-frequency node-to-node health checks and direct commands.

---

### Q7: How does EchoVault prevent duplicate message processing in P2P and RabbitMQ?
**Answer**: Every message envelope contains a globally unique `message_id` (UUID) and a UTC timestamp. Receiving nodes maintain an in-memory idempotency cache (or DB unique constraint). When a message arrives, the node checks if `message_id` has already been processed; duplicates are safely acknowledged and ignored.

---

### Q8: What happens if RabbitMQ crashes or goes offline?
**Answer**:
- Health checks report `rabbitmq: "unhealthy"`.
- Event publication fails gracefully with logged warnings without crashing the application.
- Direct gRPC RPC calls, P2P direct channels, and WebRTC live multimedia streams continue operating completely normally.

---

### Q9: What is Middleware in EchoVault?
**Answer**: Middleware is the software layer that resides between the operating system/network and the distributed application logic to provide uniform communication abstractions. In EchoVault, middleware comprises:
1. **gRPC Stubs & Skeletons** (RPC abstraction).
2. **RabbitMQ AMQP Client** (Message queuing abstraction).
3. **WebRTC Signaling & Media Pipeline** (Multimedia streaming abstraction).

---

### Q10: What are the current limitations of the FA-1 implementation?
**Answer**:
- Synthetic media generation (`DemoVideoTrack`) is used rather than physical camera drivers to guarantee reproducible testing in Docker.
- Advanced clock synchronization (Lamport / Vector clocks), distributed consensus (Raft/Paxos), and distributed file systems are not yet implemented (scheduled for FA-2).
