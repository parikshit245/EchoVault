"use client";

import { useEffect, useState } from "react";
import HeaderNav from "../../components/HeaderNav";
import styles from "./page.module.css";

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

type Unit3Report = {
  leader: string | null;
  lamport_clock: number;
  nodes: Array<{
    node_id: string;
    priority: number;
    status: string;
    lamport_clock: number;
    clock_offset_ms: number;
    last_beacon_at: string | null;
  }>;
  lock: {
    owner_node_id: string | null;
    resource_id: string | null;
    queue: string[];
  };
  elections: Array<{ leader: string | null; failed_node: string | null; completed_at: string }>;
};

type Unit4Report = {
  catalog: Array<{
    replication_id: string;
    evidence_id: string;
    owner_node_id: string;
    replica_node_id: string;
    status: string;
  }>;
  events: Array<{ event_type: string; function: string; evidence_id: string; status: string }>;
};

export default function SystemHealthPage() {
  const [health, setHealth] = useState<HealthReport | null>(null);
  const [nodes, setNodes] = useState<NodeItem[]>([]);
  const [resultMsg, setResultMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [unit3, setUnit3] = useState<Unit3Report | null>(null);
  const [unit4, setUnit4] = useState<Unit4Report | null>(null);

  const loadData = async () => {
    try {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
      const [healthRes, nodesRes, unit3Res, unit4Res] = await Promise.all([
        fetch(`${backendUrl}/health`),
        fetch(`${backendUrl}/api/v1/nodes`),
        fetch(`${backendUrl}/api/v1/unit3/state`),
        fetch(`${backendUrl}/api/v1/unit4/state`),
      ]);
      if (healthRes.ok) setHealth(await healthRes.json());
      if (nodesRes.ok) setNodes(await nodesRes.json());
      if (unit3Res.ok) setUnit3(await unit3Res.json());
      if (unit4Res.ok) setUnit4(await unit4Res.json());
    } catch {
      // ignore
    }
  };

  const runUnit3Action = async (path: string, body?: object) => {
    setBusy(true);
    setResultMsg(null);
    try {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
      const res = await fetch(`${backendUrl}${path}`, {
        method: "POST",
        headers: body ? { "Content-Type": "application/json" } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Unit 3 operation failed");
      setResultMsg(`✓ ${path.replace("/api/v1/unit3/", "").replaceAll("/", " ")} completed.`);
      await loadData();
    } catch (err) {
      setResultMsg(`✗ ${err instanceof Error ? err.message : "Unit 3 operation failed"}`);
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
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
      const res = await fetch(`${backendUrl}/api/v1/demo/seed`, { method: "POST" });
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
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
      const res = await fetch(`${backendUrl}/api/v1/demo/simulate/node-status`, {
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
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
      const res = await fetch(`${backendUrl}/api/v1/demo/reset`, { method: "POST" });
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
              <span className={styles.healthBadgeOk}>
                ● {services.grpc.toUpperCase()}
              </span>
            </div>

            <div className={styles.healthItem}>
              <div>
                <div className={styles.healthName}>WebSocket Stream Server</div>
                <div className={styles.healthMeta}>Endpoint: /ws/events ({health?.metrics.active_ws_clients || 0} active UI stream clients)</div>
              </div>
              <span className={styles.healthBadgeOk}>
                ● {services.websocket.toUpperCase()}
              </span>
            </div>

            <div className={styles.healthItem}>
              <div>
                <div className={styles.healthName}>P2P Mesh Subsystem</div>
                <div className={styles.healthMeta}>Endpoint: /ws/peer ({health?.metrics.active_p2p_peers || 0} active direct peer links)</div>
              </div>
              <span className={styles.healthBadgeOk}>
                ● {services.p2p.toUpperCase()}
              </span>
            </div>

            <div className={styles.healthItem}>
              <div>
                <div className={styles.healthName}>WebRTC Multimedia Subsystem</div>
                <div className={styles.healthMeta}>Endpoint: /ws/webrtc (aiortc RTP/SRTP live audio/video)</div>
              </div>
              <span className={styles.healthBadgeOk}>
                ● {services.webrtc.toUpperCase()}
              </span>
            </div>
          </div>
        </section>

        {/* Development Fault Simulator */}
        <section className={styles.panel}>
          <div className={styles.panelHeader}>
            <h2 className={styles.panelTitle}>Development Fault Simulator</h2>
            <span className={styles.panelTag}>ACADEMIC EVALUATION</span>
          </div>

          <div style={{ display: "flex", gap: "0.8rem", marginBottom: "1.2rem", flexWrap: "wrap" }}>
            <button className={styles.btnPrimary} onClick={handleReset} disabled={busy}>
              🧹 Clean DB &amp; Re-Seed (Purge Old Nodes)
            </button>
            <button
              className={styles.actionBtn}
              style={{ background: "rgba(255,255,255,0.08)", color: "#fff", padding: "0.65rem 1rem" }}
              onClick={handleSeed}
              disabled={busy}
            >
              🌱 Re-Seed (Idempotent)
            </button>
          </div>

          <p style={{ fontSize: "0.82rem", color: "#8da2be", margin: "0 0 0.8rem 0" }}>
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

      <div className={styles.mainGrid} style={{ marginTop: "2rem" }}>
        <section className={styles.panel}>
          <div className={styles.panelHeader}>
            <h2 className={styles.panelTitle}>Unit 3 Coordination Lab</h2>
            <span className={styles.panelTag}>LOGICAL TIME · ELECTION · MUTEX</span>
          </div>
          <p className={styles.healthMeta}>
            Lamport clock: <strong>{unit3?.lamport_clock ?? "—"}</strong> · Current leader:{" "}
            <strong>{unit3?.leader ?? "NONE"}</strong>
          </p>
          <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap", margin: "1rem 0" }}>
            <button className={styles.btnPrimary} onClick={() => runUnit3Action("/api/v1/unit3/election", { failed_node_id: unit3?.leader })} disabled={busy}>
              Run Bully Election
            </button>
            <button className={styles.btnPrimary} onClick={() => runUnit3Action("/api/v1/unit3/snapshot")} disabled={busy}>
              Capture Global Snapshot
            </button>
            <button className={styles.actionBtn} onClick={() => runUnit3Action("/api/v1/unit3/beacon", { node_id: "CCTV-A" })} disabled={busy}>
              Send Beacon
            </button>
          </div>
          <div className={styles.tableWrap}>
            <table className={styles.simTable}>
              <thead><tr><th className={styles.th}>Node</th><th className={styles.th}>Lamport</th><th className={styles.th}>Offset</th><th className={styles.th}>Beacon</th></tr></thead>
              <tbody>
                {unit3?.nodes.map((node) => (
                  <tr key={node.node_id}>
                    <td className={styles.td}><strong>{node.node_id}</strong></td>
                    <td className={styles.td}>{node.lamport_clock}</td>
                    <td className={styles.td}>{node.clock_offset_ms} ms</td>
                    <td className={styles.td}>{node.last_beacon_at ? "RECEIVED" : "PENDING"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className={styles.healthMeta} style={{ marginTop: "1rem" }}>
            Mutex: {unit3?.lock.owner_node_id ? `${unit3.lock.owner_node_id} owns ${unit3.lock.resource_id}` : "AVAILABLE"} · Queue: {unit3?.lock.queue.join(", ") || "empty"}
          </p>
          <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap" }}>
            <button className={styles.actionBtn} onClick={() => runUnit3Action("/api/v1/unit3/lock/request", { node_id: "CCTV-A", resource_id: "INC-000001" })} disabled={busy}>Request Incident Lock</button>
            <button className={styles.actionBtn} onClick={() => runUnit3Action("/api/v1/unit3/lock/release", { node_id: "CCTV-A" })} disabled={busy}>Release Incident Lock</button>
          </div>
        </section>

        <section className={styles.panel}>
          <div className={styles.panelHeader}>
            <h2 className={styles.panelTitle}>Unit 4 Evidence Replication</h2>
            <span className={styles.panelTag}>DISTRIBUTED FILE · SERVERLESS</span>
          </div>
          <p className={styles.healthMeta}>
            Event-driven replication worker records metadata, checksum, owner, and replica location without moving media through RabbitMQ.
          </p>
          <button
            className={styles.btnPrimary}
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
                const res = await fetch(`${backendUrl}/api/v1/unit4/replication/request`, {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ evidence_id: "EV-DEMO-001", owner_node_id: "CCTV-A", target_node_id: "CCTV-B", file_name: "demo-evidence.jpg", file_size: 2048 }),
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || "Replication failed");
                setResultMsg(`✓ Evidence ${data.evidence_id} replicated to ${data.replica_node_id}.`);
                await loadData();
              } catch (err) {
                setResultMsg(`✗ ${err instanceof Error ? err.message : "Replication failed"}`);
              } finally {
                setBusy(false);
              }
            }}
          >
            Replicate Demo Evidence
          </button>
          <div className={styles.tableWrap}>
            <table className={styles.simTable}>
              <thead><tr><th className={styles.th}>Evidence</th><th className={styles.th}>Owner</th><th className={styles.th}>Replica</th><th className={styles.th}>Status</th></tr></thead>
              <tbody>
                {unit4?.catalog.map((record) => (
                  <tr key={record.replication_id ?? record.evidence_id}>
                    <td className={styles.td}>{record.evidence_id}</td>
                    <td className={styles.td}>{record.owner_node_id}</td>
                    <td className={styles.td}>{record.replica_node_id}</td>
                    <td className={styles.td}><span className={styles.healthBadgeOk}>● {record.status}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className={styles.healthMeta} style={{ marginTop: "1rem" }}>
            Functions: {unit4?.events.length ?? 0} completed event-driven jobs.
          </p>
        </section>
      </div>
    </main>
  );
}
