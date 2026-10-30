"use client";

import { useEffect, useState, type ReactNode } from "react";
import HeaderNav from "../../components/HeaderNav";
import styles from "./page.module.css";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
const FALLBACK_NODE_IDS = ["SECURITY-A", "CCTV-A", "CCTV-B", "MOBILE-A"];

type HealthReport = {
  status: string;
  services: {
    database: string;
    rabbitmq: string;
    grpc: string;
    websocket: string;
    p2p: string;
    webrtc: string;
  };
  metrics: {
    registered_nodes: number;
    online_nodes: number;
    active_incidents: number;
    evidence_count: number;
    active_p2p_peers: number;
    active_webrtc_sessions: number;
    active_ws_clients: number;
  };
};

type NodeItem = {
  node_id: string;
  node_name: string;
  node_type: string;
  status: string;
};

type LockState = {
  owner_node_id: string | null;
  resource_id: string | null;
  queue: string[];
};

type Unit3Node = {
  node_id: string;
  priority: number;
  status: string;
  lamport_clock: number;
  clock_offset_ms: number;
  last_beacon_at: string | null;
};

type Unit3Report = {
  leader: string | null;
  lamport_clock: number;
  coordinator_time_ms: number;
  nodes: Unit3Node[];
  lock: LockState;
  elections: Array<{
    election_id: string;
    leader: string | null;
    failed_node: string | null;
    completed_at: string;
  }>;
  last_snapshot: {
    snapshot_id: string;
    captured_at: string;
    leader: string | null;
    lamport_clock: number;
    lock: LockState;
    nodes: Record<string, Unit3Node>;
  } | null;
};

type ReplicaRecord = {
  replication_id: string;
  evidence_id: string;
  owner_node_id: string;
  replica_node_id: string;
  file_name: string | null;
  file_size: number | null;
  checksum: string;
  status: string;
  created_at: string;
};

type Unit4Report = {
  catalog: ReplicaRecord[];
  events: Array<{
    event_id: string;
    event_type: string;
    function: string;
    evidence_id: string;
    status: string;
    timestamp: string;
  }>;
  functions: string[];
};

type Feedback = { tone: "ok" | "error"; text: string } | null;

// FastAPI returns string details for handled errors and a list for request validation errors.
const errorText = (detail: unknown, fallback: string): string => {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item: { loc?: unknown[]; msg?: string }) => {
        const field = item.loc?.[item.loc.length - 1];
        return field ? `${String(field)}: ${item.msg ?? "invalid value"}` : (item.msg ?? "invalid value");
      })
      .join("; ");
  }
  return fallback;
};

async function apiCall<T>(path: string, method: "GET" | "POST" = "GET", body?: object): Promise<T> {
  const res = await fetch(`${BACKEND_URL}${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(errorText(data.detail, `Request failed with HTTP ${res.status}`));
  return data as T;
}

async function getJson<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${BACKEND_URL}${path}`);
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className={styles.field}>
      <span className={styles.label}>{label}</span>
      {children}
    </label>
  );
}

function Block({ title, wide, children }: { title: string; wide?: boolean; children: ReactNode }) {
  return (
    <div className={wide ? `${styles.block} ${styles.blockWide}` : styles.block}>
      <h3 className={styles.blockTitle}>{title}</h3>
      {children}
    </div>
  );
}

function FeedbackBox({ msg }: { msg: Feedback }) {
  if (!msg) return null;
  return <div className={msg.tone === "ok" ? styles.feedbackOk : styles.feedbackErr}>{msg.text}</div>;
}

export default function SystemHealthPage() {
  const [health, setHealth] = useState<HealthReport | null>(null);
  const [nodes, setNodes] = useState<NodeItem[]>([]);
  const [resultMsg, setResultMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [unit3, setUnit3] = useState<Unit3Report | null>(null);
  const [unit4, setUnit4] = useState<Unit4Report | null>(null);
  const [u3Msg, setU3Msg] = useState<Feedback>(null);
  const [u4Msg, setU4Msg] = useState<Feedback>(null);

  // Unit 3 form inputs
  const [clockNode, setClockNode] = useState("CCTV-A");
  const [receivedClock, setReceivedClock] = useState("");
  const [syncNode, setSyncNode] = useState("CCTV-B");
  const [lockNode, setLockNode] = useState("CCTV-A");
  const [lockResource, setLockResource] = useState("INC-000001");

  // Unit 4 form inputs
  const [replicaForm, setReplicaForm] = useState({
    evidenceId: "EV-DEMO-001",
    owner: "CCTV-A",
    target: "CCTV-B",
    fileName: "demo-evidence.jpg",
    fileSize: "2048",
    checksum: "",
  });
  const [lookupId, setLookupId] = useState("");

  const nodeIds = unit3?.nodes.map((node) => node.node_id) ?? FALLBACK_NODE_IDS;

  // Each panel loads independently, so one failing endpoint does not blank the others.
  const loadData = async () => {
    const [healthData, nodesData, unit3Data, unit4Data] = await Promise.all([
      getJson<HealthReport>("/health"),
      getJson<NodeItem[]>("/api/v1/nodes"),
      getJson<Unit3Report>("/api/v1/unit3/state"),
      getJson<Unit4Report>("/api/v1/unit4/state"),
    ]);
    if (healthData) setHealth(healthData);
    if (nodesData) setNodes(nodesData);
    if (unit3Data) setUnit3(unit3Data);
    if (unit4Data) setUnit4(unit4Data);
  };

  // Runs one POST action and reports its outcome in the given panel.
  const runAction = async (
    setMsg: (msg: Feedback) => void,
    path: string,
    body: object | undefined,
    describe: (data: Record<string, unknown>) => string,
  ) => {
    setBusy(true);
    setMsg(null);
    try {
      const data = await apiCall<Record<string, unknown>>(path, "POST", body);
      setMsg({ tone: "ok", text: `✓ ${describe(data)}` });
      await loadData();
    } catch (err) {
      setMsg({ tone: "error", text: `✗ ${err instanceof Error ? err.message : "Request failed"}` });
    } finally {
      setBusy(false);
    }
  };

  // Cristian: read the coordinator time, measure the round trip, then send both to the sync endpoint.
  const synchronizeClock = async () => {
    setBusy(true);
    setU3Msg(null);
    try {
      const started = performance.now();
      const state = await apiCall<Unit3Report>("/api/v1/unit3/state");
      const roundTripMs = performance.now() - started;
      const result = await apiCall<{ offset_ms: number; round_trip_ms: number }>(
        "/api/v1/unit3/clock/synchronize",
        "POST",
        {
          node_id: syncNode,
          reference_time_ms: state.coordinator_time_ms,
          round_trip_ms: roundTripMs,
        },
      );
      setU3Msg({
        tone: "ok",
        text: `✓ ${syncNode} synchronized with coordinator: offset ${result.offset_ms} ms, round trip ${result.round_trip_ms} ms.`,
      });
      await loadData();
    } catch (err) {
      setU3Msg({ tone: "error", text: `✗ ${err instanceof Error ? err.message : "Clock sync failed"}` });
    } finally {
      setBusy(false);
    }
  };

  const lookupReplica = async () => {
    const evidenceId = lookupId.trim();
    if (!evidenceId) {
      setU4Msg({ tone: "error", text: "✗ Enter an evidence ID to look up." });
      return;
    }
    setBusy(true);
    setU4Msg(null);
    try {
      const record = await apiCall<ReplicaRecord>(`/api/v1/unit4/replication/${encodeURIComponent(evidenceId)}`);
      setU4Msg({
        tone: "ok",
        text: `✓ ${record.evidence_id} is replicated: owner ${record.owner_node_id}, replica ${record.replica_node_id}, status ${record.status}.`,
      });
    } catch (err) {
      setU4Msg({ tone: "error", text: `✗ ${err instanceof Error ? err.message : "Lookup failed"}` });
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    // The diagnostics console intentionally refreshes remote state on mount.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadData();
    const interval = setInterval(() => void loadData(), 2500);
    return () => clearInterval(interval);
  }, []);

  const handleSeed = async () => {
    setBusy(true);
    setResultMsg(null);
    try {
      const res = await fetch(`${BACKEND_URL}/api/v1/demo/seed`, { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Seeding failed");
      setResultMsg("✓ Demo environment successfully seeded with 4 nodes, INC-000001, and 4 evidence items.");
      await loadData();
    } catch (err) {
      setResultMsg(`✗ ${err instanceof Error ? err.message : "Seeding failed"}`);
    } finally {
      setBusy(false);
    }
  };

  const handleToggleNode = async (nodeId: string, currentStatus: string) => {
    setBusy(true);
    setResultMsg(null);
    const targetStatus = currentStatus === "ONLINE" ? "OFFLINE" : "ONLINE";
    try {
      const res = await fetch(`${BACKEND_URL}/api/v1/demo/simulate/node-status`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ node_id: nodeId, status: targetStatus }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Simulation failed");
      setResultMsg(`✓ Node ${nodeId} simulated transition to ${targetStatus}. Published node.status_changed event.`);
      await loadData();
    } catch (err) {
      setResultMsg(`✗ ${err instanceof Error ? err.message : "Simulation failed"}`);
    } finally {
      setBusy(false);
    }
  };

  const handleReset = async () => {
    setBusy(true);
    setResultMsg(null);
    try {
      const res = await fetch(`${BACKEND_URL}/api/v1/demo/reset`, { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Reset failed");
      setResultMsg("✓ All demo nodes restored to ONLINE and incident state refreshed.");
      await loadData();
    } catch (err) {
      setResultMsg(`✗ ${err instanceof Error ? err.message : "Reset failed"}`);
    } finally {
      setBusy(false);
    }
  };

  const services = health?.services || {
    database: "healthy",
    rabbitmq: "healthy",
    grpc: "running",
    websocket: "healthy",
    p2p: "healthy",
    webrtc: "ready",
  };

  const lastElection = unit3?.elections[0];

  return (
    <main className={styles.page}>
      <HeaderNav />

      <section className={styles.hero}>
        <p className={styles.kicker}>HEALTH MONITOR &amp; FAULT SIMULATION</p>
        <h1 className={styles.title}>System Diagnostics Console</h1>
        <p className={styles.subtitle}>
          Verify connectivity across all six distributed communication layers. Use the development fault
          simulator to test distributed system behavior during node outages and recovery.
        </p>
      </section>

      {resultMsg && <div className={styles.resultBox}>{resultMsg}</div>}

      <div className={styles.mainGrid}>
        {/* Subsystem Health Monitor */}
        <section className={styles.panel}>
          <div className={styles.panelHeader}>
            <h2 className={styles.panelTitle}>Subsystem Health Monitor</h2>
            <span className={styles.panelTag}>REAL-TIME</span>
          </div>

          <div className={styles.healthList}>
            <div className={styles.healthItem}>
              <div>
                <div className={styles.healthName}>Neon PostgreSQL Database</div>
                <div className={styles.healthMeta}>Evidence metadata, incident registry &amp; audit tables</div>
              </div>
              <span className={services.database === "healthy" ? styles.healthBadgeOk : styles.healthBadgeErr}>
                ● {services.database.toUpperCase()}
              </span>
            </div>

            <div className={styles.healthItem}>
              <div>
                <div className={styles.healthName}>RabbitMQ Broker (AMQP 0-9-1)</div>
                <div className={styles.healthMeta}>Exchange: echovault.events (Durable topic pub/sub)</div>
              </div>
              <span className={services.rabbitmq === "healthy" ? styles.healthBadgeOk : styles.healthBadgeErr}>
                ● {services.rabbitmq.toUpperCase()}
              </span>
            </div>

            <div className={styles.healthItem}>
              <div>
                <div className={styles.healthName}>gRPC RPC Server (HTTP/2)</div>
                <div className={styles.healthMeta}>Inter-node synchronous procedure calls (Port 50051)</div>
              </div>
              <span className={styles.healthBadgeOk}>● {services.grpc.toUpperCase()}</span>
            </div>

            <div className={styles.healthItem}>
              <div>
                <div className={styles.healthName}>WebSocket Stream Server</div>
                <div className={styles.healthMeta}>Endpoint: /ws/events ({health?.metrics.active_ws_clients || 0} active UI stream clients)</div>
              </div>
              <span className={styles.healthBadgeOk}>● {services.websocket.toUpperCase()}</span>
            </div>

            <div className={styles.healthItem}>
              <div>
                <div className={styles.healthName}>P2P Mesh Subsystem</div>
                <div className={styles.healthMeta}>Endpoint: /ws/peer ({health?.metrics.active_p2p_peers || 0} active direct peer links)</div>
              </div>
              <span className={styles.healthBadgeOk}>● {services.p2p.toUpperCase()}</span>
            </div>

            <div className={styles.healthItem}>
              <div>
                <div className={styles.healthName}>WebRTC Multimedia Subsystem</div>
                <div className={styles.healthMeta}>Endpoint: /ws/webrtc (aiortc RTP/SRTP live audio/video)</div>
              </div>
              <span className={styles.healthBadgeOk}>● {services.webrtc.toUpperCase()}</span>
            </div>
          </div>
        </section>

        {/* Development Fault Simulator */}
        <section className={styles.panel}>
          <div className={styles.panelHeader}>
            <h2 className={styles.panelTitle}>Development Fault Simulator</h2>
            <span className={styles.panelTag}>ACADEMIC EVALUATION</span>
          </div>

          <div className={styles.actionRow}>
            <button className={styles.btnPrimary} onClick={handleReset} disabled={busy}>
              🧹 Clean DB &amp; Re-Seed (Purge Old Nodes)
            </button>
            <button className={styles.btnSecondary} onClick={handleSeed} disabled={busy}>
              🌱 Re-Seed (Idempotent)
            </button>
          </div>

          <p className={styles.note}>
            Simulate a node crash or recovery to demonstrate how the rest of EchoVault continues
            functioning independently:
          </p>

          <div className={styles.tableWrap}>
            <table className={styles.simTable}>
              <thead>
                <tr>
                  <th className={styles.th}>Node ID</th>
                  <th className={styles.th}>Type</th>
                  <th className={styles.th}>Current Status</th>
                  <th className={styles.th}>Action</th>
                </tr>
              </thead>
              <tbody>
                {nodes.map((node) => (
                  <tr key={node.node_id}>
                    <td className={styles.td}><strong>{node.node_id}</strong></td>
                    <td className={styles.td}>{node.node_type}</td>
                    <td className={styles.td}>
                      <span className={node.status === "ONLINE" ? styles.healthBadgeOk : styles.healthBadgeErr}>
                        ● {node.status}
                      </span>
                    </td>
                    <td className={styles.td}>
                      {node.status === "ONLINE" ? (
                        <button
                          className={`${styles.actionBtn} ${styles.btnFail}`}
                          onClick={() => handleToggleNode(node.node_id, "ONLINE")}
                          disabled={busy}
                        >
                          Simulate Crash (Offline)
                        </button>
                      ) : (
                        <button
                          className={`${styles.actionBtn} ${styles.btnRecover}`}
                          onClick={() => handleToggleNode(node.node_id, "OFFLINE")}
                          disabled={busy}
                        >
                          Recover Node (Online)
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      {/* ── Unit 3 · Distributed Coordination ─────────────────────────── */}
      <section className={styles.unitSection}>
        <div className={styles.unitHeader}>
          <div>
            <p className={styles.kicker}>UNIT 3 · SYNCHRONIZATION &amp; COORDINATION</p>
            <h2 className={styles.unitTitle}>Coordination Lab</h2>
            <p className={styles.subtitle}>
              Four-node topology with priorities, Lamport logical clocks, Cristian synchronization,
              heartbeats, Bully election, coordinator-based mutual exclusion and marker-based snapshots.
            </p>
          </div>
          <button
            className={styles.btnSecondary}
            disabled={busy}
            onClick={() => runAction(setU3Msg, "/api/v1/unit3/reset", undefined, () => "Unit 3 state reset to initial values.")}
          >
            Reset Unit 3 State
          </button>
        </div>

        <div className={styles.statRow}>
          <div className={styles.stat}>
            <span className={styles.statLabel}>Lamport clock</span>
            <span className={styles.statValue}>{unit3?.lamport_clock ?? "—"}</span>
          </div>
          <div className={styles.stat}>
            <span className={styles.statLabel}>Leader</span>
            <span className={styles.statValue}>{unit3?.leader ?? "NONE"}</span>
          </div>
          <div className={styles.stat}>
            <span className={styles.statLabel}>Lock owner</span>
            <span className={styles.statValue}>
              {unit3?.lock.owner_node_id ? `${unit3.lock.owner_node_id}` : "AVAILABLE"}
            </span>
          </div>
          <div className={styles.stat}>
            <span className={styles.statLabel}>Lock queue</span>
            <span className={styles.statValue}>{unit3?.lock.queue.length ?? 0} waiting</span>
          </div>
        </div>

        <div className={styles.blockGrid}>
          <Block title="Topology, Priorities &amp; Node Failure" wide>
            <p className={styles.note}>
              Bully election picks the highest-priority ONLINE node. &quot;Fail Node &amp; Re-elect&quot; marks a node
              OFFLINE and elects a new leader; &quot;Send Beacon&quot; is the heartbeat that brings it back ONLINE.
            </p>
            <div className={styles.tableWrap}>
              <table className={styles.simTable}>
                <thead>
                  <tr>
                    <th className={styles.th}>Node</th>
                    <th className={styles.th}>Priority</th>
                    <th className={styles.th}>Status</th>
                    <th className={styles.th}>Lamport</th>
                    <th className={styles.th}>Clock offset</th>
                    <th className={styles.th}>Last beacon</th>
                    <th className={styles.th}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {unit3?.nodes.map((node) => (
                    <tr key={node.node_id}>
                      <td className={styles.td}>
                        <strong>{node.node_id}</strong>
                        {node.node_id === unit3?.leader && <span className={styles.leaderTag}>LEADER</span>}
                      </td>
                      <td className={styles.td}>{node.priority}</td>
                      <td className={styles.td}>
                        <span className={node.status === "ONLINE" ? styles.healthBadgeOk : styles.healthBadgeErr}>
                          ● {node.status}
                        </span>
                      </td>
                      <td className={styles.td}>{node.lamport_clock}</td>
                      <td className={styles.td}>{node.clock_offset_ms} ms</td>
                      <td className={styles.td}>
                        {node.last_beacon_at ? new Date(node.last_beacon_at).toLocaleTimeString() : "Never"}
                      </td>
                      <td className={styles.td}>
                        <div className={styles.rowActions}>
                          <button
                            className={`${styles.actionBtn} ${styles.btnRecover}`}
                            disabled={busy}
                            onClick={() =>
                              runAction(
                                setU3Msg,
                                "/api/v1/unit3/beacon",
                                { node_id: node.node_id },
                                () => `${node.node_id} beacon received; status ONLINE.`,
                              )
                            }
                          >
                            Send Beacon
                          </button>
                          <button
                            className={`${styles.actionBtn} ${styles.btnFail}`}
                            disabled={busy || node.status !== "ONLINE"}
                            onClick={() =>
                              runAction(
                                setU3Msg,
                                "/api/v1/unit3/election",
                                { failed_node_id: node.node_id },
                                (d) => `${node.node_id} failed; Bully election chose leader ${String(d.leader)}.`,
                              )
                            }
                          >
                            Fail Node &amp; Re-elect
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Block>

          <Block title="Lamport Logical Clock">
            <p className={styles.note}>
              A local event ticks the clock. With a received timestamp, the node merges it as
              max(local, received) + 1.
            </p>
            <div className={styles.formRow}>
              <Field label="Node">
                <select className={styles.input} value={clockNode} onChange={(e) => setClockNode(e.target.value)}>
                  {nodeIds.map((id) => (
                    <option key={id} value={id}>{id}</option>
                  ))}
                </select>
              </Field>
              <Field label="Received timestamp (optional)">
                <input
                  className={styles.input}
                  type="number"
                  min={0}
                  placeholder="e.g. 8"
                  value={receivedClock}
                  onChange={(e) => setReceivedClock(e.target.value)}
                />
              </Field>
            </div>
            <div className={styles.actionRow}>
              <button
                className={styles.btnPrimary}
                disabled={busy}
                onClick={() =>
                  runAction(
                    setU3Msg,
                    "/api/v1/unit3/clock/tick",
                    { node_id: clockNode, received_clock: receivedClock === "" ? null : Number(receivedClock) },
                    (d) =>
                      receivedClock === ""
                        ? `${clockNode} local event; Lamport clock is now ${String(d.lamport_clock)}.`
                        : `${clockNode} merged received timestamp ${receivedClock}; Lamport clock is now ${String(d.lamport_clock)}.`,
                  )
                }
              >
                Tick Lamport Clock
              </button>
            </div>
          </Block>

          <Block title="Cristian Clock Synchronization">
            <p className={styles.note}>
              The node reads the coordinator time, measures the round trip, and sets its offset to
              coordinator time − (local time − RTT / 2).
            </p>
            <div className={styles.formRow}>
              <Field label="Node">
                <select className={styles.input} value={syncNode} onChange={(e) => setSyncNode(e.target.value)}>
                  {nodeIds.map((id) => (
                    <option key={id} value={id}>{id}</option>
                  ))}
                </select>
              </Field>
            </div>
            <div className={styles.actionRow}>
              <button className={styles.btnPrimary} disabled={busy} onClick={synchronizeClock}>
                Synchronize Clock
              </button>
            </div>
          </Block>

          <Block title="Bully Leader Election">
            <p className={styles.note}>
              Run an election with all nodes ONLINE, or fail the current leader to force re-election.
            </p>
            <div className={styles.actionRow}>
              <button
                className={styles.btnPrimary}
                disabled={busy}
                onClick={() =>
                  runAction(setU3Msg, "/api/v1/unit3/election", {}, (d) => `Election ${String(d.election_id)} chose leader ${String(d.leader)}.`)
                }
              >
                Run Election
              </button>
              <button
                className={styles.btnFailLarge}
                disabled={busy || !unit3?.leader}
                onClick={() =>
                  runAction(
                    setU3Msg,
                    "/api/v1/unit3/election",
                    { failed_node_id: unit3?.leader },
                    (d) => `Leader ${String(d.failed_node)} failed; new leader is ${String(d.leader)}.`,
                  )
                }
              >
                Fail Current Leader
              </button>
            </div>
            <p className={styles.note}>
              {lastElection
                ? `Last election ${lastElection.election_id}: leader ${lastElection.leader ?? "NONE"}${
                    lastElection.failed_node ? `, failed node ${lastElection.failed_node}` : ""
                  }.`
                : "No election has run yet."}
            </p>
          </Block>

          <Block title="Coordinator-Based Mutual Exclusion">
            <p className={styles.note}>
              The coordinator grants one lock at a time. Other requests wait in a FIFO queue, and a release
              promotes the next waiter. Only the owner can release.
            </p>
            <div className={styles.formRow}>
              <Field label="Node">
                <select className={styles.input} value={lockNode} onChange={(e) => setLockNode(e.target.value)}>
                  {nodeIds.map((id) => (
                    <option key={id} value={id}>{id}</option>
                  ))}
                </select>
              </Field>
              <Field label="Resource ID">
                <input
                  className={styles.input}
                  value={lockResource}
                  maxLength={200}
                  onChange={(e) => setLockResource(e.target.value)}
                />
              </Field>
            </div>
            <div className={styles.actionRow}>
              <button
                className={styles.btnPrimary}
                disabled={busy}
                onClick={() =>
                  runAction(
                    setU3Msg,
                    "/api/v1/unit3/lock/request",
                    { node_id: lockNode, resource_id: lockResource },
                    (d) =>
                      d.granted
                        ? `${lockNode} acquired lock on ${lockResource}.`
                        : `${lockNode} queued for ${lockResource}; owner is ${String(d.owner_node_id)}.`,
                  )
                }
              >
                Request Lock
              </button>
              <button
                className={styles.btnSecondary}
                disabled={busy}
                onClick={() =>
                  runAction(
                    setU3Msg,
                    "/api/v1/unit3/lock/release",
                    { node_id: lockNode },
                    (d) => `${lockNode} released the lock; next owner is ${d.owner_node_id ? String(d.owner_node_id) : "none"}.`,
                  )
                }
              >
                Release Lock
              </button>
            </div>
            <p className={styles.note}>
              Owner: {unit3?.lock.owner_node_id ?? "none"} · Resource: {unit3?.lock.resource_id ?? "—"} · Queue:{" "}
              {unit3?.lock.queue.join(", ") || "empty"}
            </p>
          </Block>

          <Block title="Marker-Based Global Snapshot">
            <p className={styles.note}>
              Captures the leader, Lamport clock, lock state and every node&apos;s status as one global state.
            </p>
            <div className={styles.actionRow}>
              <button
                className={styles.btnPrimary}
                disabled={busy}
                onClick={() => runAction(setU3Msg, "/api/v1/unit3/snapshot", undefined, (d) => `Snapshot ${String(d.snapshot_id)} captured.`)}
              >
                Capture Global Snapshot
              </button>
            </div>
            {unit3?.last_snapshot ? (
              <p className={styles.note}>
                Snapshot {unit3.last_snapshot.snapshot_id} at {new Date(unit3.last_snapshot.captured_at).toLocaleTimeString()}:
                leader {unit3.last_snapshot.leader ?? "NONE"}, Lamport {unit3.last_snapshot.lamport_clock}, lock owner{" "}
                {unit3.last_snapshot.lock.owner_node_id ?? "none"}, {Object.keys(unit3.last_snapshot.nodes).length} nodes recorded.
              </p>
            ) : (
              <p className={styles.note}>No snapshot captured yet.</p>
            )}
          </Block>
        </div>

        <FeedbackBox msg={u3Msg} />
      </section>

      {/* ── Unit 4 · Evidence Replication ─────────────────────────────── */}
      <section className={styles.unitSection}>
        <div className={styles.unitHeader}>
          <div>
            <p className={styles.kicker}>UNIT 4 · EMERGING PARADIGMS</p>
            <h2 className={styles.unitTitle}>Evidence Replication Catalog</h2>
            <p className={styles.subtitle}>
              Event-driven replication worker records owner, replica target, file details and checksum for each
              evidence item, then publishes a replication.completed event.
            </p>
          </div>
          <button
            className={styles.btnSecondary}
            disabled={busy}
            onClick={() => runAction(setU4Msg, "/api/v1/unit4/reset", undefined, () => "Replication catalog and events cleared.")}
          >
            Reset Replication Catalog
          </button>
        </div>

        <div className={styles.blockGrid}>
          <Block title="Request Evidence Replication">
            <div className={styles.formGrid}>
              <Field label="Evidence ID">
                <input
                  className={styles.input}
                  value={replicaForm.evidenceId}
                  maxLength={80}
                  onChange={(e) => setReplicaForm({ ...replicaForm, evidenceId: e.target.value })}
                />
              </Field>
              <Field label="Owner node">
                <select
                  className={styles.input}
                  value={replicaForm.owner}
                  onChange={(e) => setReplicaForm({ ...replicaForm, owner: e.target.value })}
                >
                  {nodeIds.map((id) => (
                    <option key={id} value={id}>{id}</option>
                  ))}
                </select>
              </Field>
              <Field label="Replica target node">
                <select
                  className={styles.input}
                  value={replicaForm.target}
                  onChange={(e) => setReplicaForm({ ...replicaForm, target: e.target.value })}
                >
                  {nodeIds.map((id) => (
                    <option key={id} value={id}>{id}</option>
                  ))}
                </select>
              </Field>
              <Field label="File name">
                <input
                  className={styles.input}
                  value={replicaForm.fileName}
                  onChange={(e) => setReplicaForm({ ...replicaForm, fileName: e.target.value })}
                />
              </Field>
              <Field label="File size (bytes)">
                <input
                  className={styles.input}
                  type="number"
                  min={0}
                  value={replicaForm.fileSize}
                  onChange={(e) => setReplicaForm({ ...replicaForm, fileSize: e.target.value })}
                />
              </Field>
              <Field label="Checksum (optional)">
                <input
                  className={styles.input}
                  placeholder="Blank = automatic SHA-256"
                  value={replicaForm.checksum}
                  onChange={(e) => setReplicaForm({ ...replicaForm, checksum: e.target.value })}
                />
              </Field>
            </div>
            <div className={styles.actionRow}>
              <button
                className={styles.btnPrimary}
                disabled={busy}
                onClick={() =>
                  runAction(
                    setU4Msg,
                    "/api/v1/unit4/replication/request",
                    {
                      evidence_id: replicaForm.evidenceId,
                      owner_node_id: replicaForm.owner,
                      target_node_id: replicaForm.target,
                      file_name: replicaForm.fileName || null,
                      file_size: replicaForm.fileSize === "" ? null : Number(replicaForm.fileSize),
                      checksum: replicaForm.checksum || null,
                    },
                    (d) =>
                      `${String(d.replication_id)}: ${String(d.evidence_id)} replicated ${String(d.owner_node_id)} → ${String(
                        d.replica_node_id,
                      )}. Checksum ${String(d.checksum).slice(0, 16)}…${replicaForm.checksum ? "" : " (automatic SHA-256)"}`,
                  )
                }
              >
                Replicate Evidence
              </button>
            </div>
          </Block>

          <Block title="Replica Lookup">
            <p className={styles.note}>Look up the replica record for an evidence ID. Unknown IDs return a not-found error.</p>
            <div className={styles.formRow}>
              <Field label="Evidence ID">
                <input
                  className={styles.input}
                  placeholder="EV-DEMO-001"
                  value={lookupId}
                  onChange={(e) => setLookupId(e.target.value)}
                />
              </Field>
            </div>
            <div className={styles.actionRow}>
              <button className={styles.btnPrimary} disabled={busy} onClick={lookupReplica}>
                Look Up Replica
              </button>
            </div>
          </Block>
        </div>

        <FeedbackBox msg={u4Msg} />

        <Block title="Replication Catalog">
          <div className={styles.tableWrap}>
            <table className={styles.simTable}>
              <thead>
                <tr>
                  <th className={styles.th}>Replication ID</th>
                  <th className={styles.th}>Evidence</th>
                  <th className={styles.th}>Owner → Replica</th>
                  <th className={styles.th}>File</th>
                  <th className={styles.th}>Checksum</th>
                  <th className={styles.th}>Status</th>
                  <th className={styles.th}>Created</th>
                </tr>
              </thead>
              <tbody>
                {unit4?.catalog.length ? (
                  unit4.catalog.map((record) => (
                    <tr key={record.replication_id}>
                      <td className={styles.td}>{record.replication_id}</td>
                      <td className={styles.td}>{record.evidence_id}</td>
                      <td className={styles.td}>{record.owner_node_id} → {record.replica_node_id}</td>
                      <td className={styles.td}>
                        {record.file_name ?? "—"}
                        {record.file_size !== null ? ` (${record.file_size} B)` : ""}
                      </td>
                      <td className={styles.td}><code className={styles.code}>{record.checksum.slice(0, 16)}…</code></td>
                      <td className={styles.td}><span className={styles.healthBadgeOk}>● {record.status}</span></td>
                      <td className={styles.td}>{new Date(record.created_at).toLocaleTimeString()}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td className={styles.td} colSpan={7}>No replicas recorded yet. Use &quot;Replicate Evidence&quot; above.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Block>

        <div className={styles.blockGrid}>
          <Block title="Event-Driven Replication Events">
            <div className={styles.tableWrap}>
              <table className={styles.simTable}>
                <thead>
                  <tr>
                    <th className={styles.th}>Event</th>
                    <th className={styles.th}>Function</th>
                    <th className={styles.th}>Evidence</th>
                    <th className={styles.th}>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {unit4?.events.length ? (
                    unit4.events.map((event) => (
                      <tr key={event.event_id}>
                        <td className={styles.td}>{event.event_type}</td>
                        <td className={styles.td}><code className={styles.code}>{event.function}</code></td>
                        <td className={styles.td}>{event.evidence_id}</td>
                        <td className={styles.td}>{event.status}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td className={styles.td} colSpan={4}>No replication.completed events yet.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </Block>

          <Block title="Worker Function Roles">
            <ul className={styles.roleList}>
              <li>
                <code className={styles.code}>replication_worker</code> handles each replication request, stores the
                owner, replica, file and checksum metadata, and publishes <em>replication.completed</em>.
              </li>
              <li>
                <code className={styles.code}>fallback_retrieval</code> is the retrieval role; the replica lookup above
                is its entry point.
              </li>
            </ul>
            <p className={styles.note}>
              Limitation: this is a metadata and event demonstration. Physical evidence files are not yet copied
              between nodes, and a blank checksum uses a SHA-256 of the evidence ID rather than file contents.
            </p>
          </Block>
        </div>
      </section>
    </main>
  );
}
