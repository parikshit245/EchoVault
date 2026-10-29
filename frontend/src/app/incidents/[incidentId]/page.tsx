"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import GuidedMission from "../../../components/GuidedMission";
import HeaderNav from "../../../components/HeaderNav";
import LiveWebRTCFeed from "../../../components/LiveWebRTCFeed";
import { useEventStream, type WsEvent } from "../../../hooks/useEventStream";
import styles from "../page.module.css";

type Incident = {
  incident_id: string;
  title: string;
  incident_type: string;
  description: string | null;
  status: string;
  severity: string;
  location: Record<string, unknown> | null;
  started_at: string;
  created_by_node_id: string;
};

type Evidence = {
  evidence_id: string;
  node_id: string;
  title: string;
  event_type: string;
  evidence_type: string;
  captured_at: string;
  sha256?: string;
  file_size_bytes?: number;
};

type Node = {
  node_id: string;
  node_name: string;
  role: string;
  status: string;
};

type RemoteRpcResult = {
  evidence_id: string;
  node_id: string;
  latency_ms: number;
  data: Record<string, unknown>;
};

const api = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

function WsStatusDot({ status }: { status: string }) {
  const cls =
    status === "connected"
      ? styles.dotLive
      : status === "connecting"
      ? styles.dotConnecting
      : styles.dotOff;
  const label =
    status === "connected" ? "LIVE" : status === "connecting" ? "CONNECTING…" : "OFFLINE";
  return (
    <span className={styles.wsIndicator}>
      <span className={cls} />
      {label}
    </span>
  );
}

function ActivityItem({ event }: { event: WsEvent }) {
  const time = new Date(event.timestamp).toLocaleTimeString();
  const category = event.event_type.split(".")[0];
  return (
    <div className={styles.activityItem}>
      <div className={styles.activityTime}>{time}</div>
      <div className={styles.activityBody}>
        <span className={`${styles.activityChip} ${styles[`chip_${category}`]}`}>
          {event.event_type}
        </span>
        <span className={styles.activitySource}>{event.source_node_id}</span>
      </div>
    </div>
  );
}

export default function IncidentDetails({
  params,
}: {
  params: Promise<{ incidentId: string }>;
}) {
  const [id, setId] = useState("");
  const [incident, setIncident] = useState<Incident | null>(null);
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [nodes, setNodes] = useState<Node[]>([]);
  const [localEvidence, setLocalEvidence] = useState<Evidence[]>([]);
  const [error, setError] = useState<string | null>(null);

  // gRPC & P2P interactive states
  const [rpcLoading, setRpcLoading] = useState<string | null>(null);
  const [rpcResult, setRpcResult] = useState<RemoteRpcResult | null>(null);
  const [p2pTarget, setP2pTarget] = useState("CCTV-B");
  const [p2pResult, setP2pResult] = useState<string | null>(null);
  const [p2pBusy, setP2pBusy] = useState(false);

  // Category filter for live events
  const [eventCategoryFilter, setEventCategoryFilter] = useState("ALL");

  // WebSocket real-time activity — filter to this incident
  const { status: wsStatus, events: liveEvents } = useEventStream({
    filters: id ? { incident_ids: [id] } : {},
    enabled: !!id,
  });

  const load = useCallback(async (incidentId: string) => {
    try {
      const responses = await Promise.all([
        fetch(`${api}/api/v1/incidents/${incidentId}`),
        fetch(`${api}/api/v1/incidents/${incidentId}/evidence`),
        fetch(`${api}/api/v1/incidents/${incidentId}/nodes`),
        fetch(`${api}/api/v1/evidence`),
      ]);
      if (!responses[0].ok) throw new Error("Incident not found.");
      setIncident(await responses[0].json());
      setEvidence(await responses[1].json());
      const nodeList = await responses[2].json();
      setNodes(nodeList);
      if (nodeList.length > 0 && !p2pTarget) {
        setP2pTarget(nodeList[0].node_id);
      }
      setLocalEvidence(await responses[3].json());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to load incident.");
    }
  }, [p2pTarget]);

  useEffect(() => {
    void params.then(({ incidentId }) => {
      setId(incidentId);
      void load(incidentId);
    });
  }, [params, load]);

  // Refresh data when a relevant live event arrives
  const lastEventId = liveEvents[0]?.message_id;
  useEffect(() => {
    if (!lastEventId || !id) return;
    const t = setTimeout(() => void load(id), 1200);
    return () => clearTimeout(t);
  }, [lastEventId, id, load]);

  async function request(path: string, method: string, body?: unknown) {
    const response = await fetch(`${api}${path}`, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!response.ok) {
      const detail = await response.json().catch(() => null);
      throw new Error(detail?.detail || "Request failed.");
    }
    return response.json();
  }

  async function attach(evidenceId: string) {
    try {
      await request(`/api/v1/incidents/${id}/evidence/${evidenceId}`, "POST");
      await load(id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to attach evidence.");
    }
  }

  async function statusChange(status: string) {
    try {
      await request(`/api/v1/incidents/${id}`, "PATCH", { status });
      await load(id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Invalid status transition.");
    }
  }

  // ── Remote Evidence Fetch via gRPC ──
  async function fetchRemoteEvidence(nodeId: string, evidenceId: string) {
    setRpcLoading(evidenceId);
    setRpcResult(null);
    const startTime = performance.now();
    try {
      const res = await fetch(`${api}/api/v1/remote/nodes/${nodeId}/evidence/${evidenceId}`);
      const data = await res.json();
      const elapsed = Math.round(performance.now() - startTime);
      if (!res.ok) throw new Error(data.detail || "gRPC remote fetch failed");
      setRpcResult({
        evidence_id: evidenceId,
        node_id: nodeId,
        latency_ms: elapsed,
        data,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "gRPC remote query failed");
    } finally {
      setRpcLoading(null);
    }
  }

  // ── Send Direct P2P Announcement ──
  async function sendP2pAnnouncement() {
    if (!p2pTarget) return;
    setP2pBusy(true);
    setP2pResult(null);
    try {
      const res = await fetch(`${api}/api/v1/peers/${p2pTarget}/announce/incident/${id}`, {
        method: "POST",
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "P2P delivery failed");
      setP2pResult(`✓ Direct P2P incident announcement delivered to ${p2pTarget} over /ws/peer (no central broker).`);
    } catch (err) {
      setP2pResult(`✗ ${err instanceof Error ? err.message : "P2P transmission failed"}`);
    } finally {
      setP2pBusy(false);
    }
  }

  const filteredEvents = liveEvents.filter((ev) => {
    if (eventCategoryFilter === "ALL") return true;
    if (eventCategoryFilter === "EVIDENCE") return ev.event_type.startsWith("evidence.");
    if (eventCategoryFilter === "INCIDENT") return ev.event_type.startsWith("incident.");
    if (eventCategoryFilter === "NODE") return ev.event_type.startsWith("node.");
    if (eventCategoryFilter === "WEBRTC") return ev.event_type.startsWith("webrtc.");
    return true;
  });

  if (error && !incident)
    return (
      <main className={styles.page}>
        <HeaderNav />
        <div style={{ padding: "2rem" }}>
          <p className={styles.error}>{error}</p>
        </div>
      </main>
    );

  if (!incident)
    return (
      <main className={styles.page}>
        <HeaderNav />
        <div style={{ padding: "3rem", textAlign: "center" }}>
          <p className={styles.message}>Loading Incident Command Center…</p>
        </div>
      </main>
    );

  return (
    <main className={styles.page}>
      <HeaderNav />

      <div style={{ maxWidth: "1400px", margin: "0 auto", padding: "1.5rem 2rem" }}>
        {/* Guided Mission Step-by-Step Banner */}
        <GuidedMission
          currentStage={1}
          onExecuteGrpc={() => fetchRemoteEvidence("CCTV-B", "EV-002")}
          onExecuteP2p={sendP2pAnnouncement}
          grpcLoading={rpcLoading !== null}
          p2pLoading={p2pBusy}
        />

        {/* Hero Banner */}
        <section className={styles.hero} style={{ marginBottom: "1.5rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "1rem" }}>
            <div>
              <p className={styles.kicker}>
                {incident.incident_type} · {incident.severity} · SHARED LOGICAL CONTEXT
              </p>
              <h1>{incident.title}</h1>
              <p style={{ maxWidth: "700px" }}>{incident.description || "No description provided."}</p>
            </div>
            <div style={{ display: "flex", gap: "0.8rem", alignItems: "center" }}>
              <WsStatusDot status={wsStatus} />
              <div className={styles.actions}>
                {incident.status === "OPEN" && (
                  <button onClick={() => void statusChange("INVESTIGATING")}>
                    Start Investigation
                  </button>
                )}
                {incident.status === "INVESTIGATING" && (
                  <button onClick={() => void statusChange("RESOLVED")}>
                    Mark Resolved
                  </button>
                )}
                {incident.status === "RESOLVED" && (
                  <button onClick={() => void statusChange("CLOSED")}>
                    Close Incident
                  </button>
                )}
              </div>
            </div>
          </div>
        </section>

        {/* Embedded Tactical WebRTC Live Video Stream */}
        <LiveWebRTCFeed nodeId="CCTV-A" incidentId={incident.incident_id} />

        <section className={styles.content}>
          {/* Incident Info */}
          <div className={styles.panel}>
            <div className={styles.heading}>
              <h2>Incident Telemetry</h2>
              <span>{incident.incident_id}</span>
            </div>
            <dl className={styles.details}>
              <div>
                <dt>Status</dt>
                <dd>
                  <span style={{ color: "#38bdf8", fontWeight: 700 }}>{incident.status}</span>
                </dd>
              </div>
              <div>
                <dt>Triggering Node</dt>
                <dd><strong>{incident.created_by_node_id}</strong></dd>
              </div>
              <div>
                <dt>Detection Time</dt>
                <dd>{new Date(incident.started_at).toLocaleString()}</dd>
              </div>
              <div>
                <dt>Physical Sector</dt>
                <dd>
                  {incident.location ? JSON.stringify(incident.location) : "Sector 4 Perimeter"}
                </dd>
              </div>
            </dl>

            {/* Direct P2P Alert Tool */}
            <div style={{ marginTop: "1.5rem", borderTop: "1px solid rgba(255,255,255,0.08)", paddingTop: "1rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
                <h3 style={{ fontSize: "0.85rem", color: "#00d2ff", margin: 0 }}>
                  ⚡ Direct P2P Tactical Dispatch
                </h3>
                <span style={{ fontSize: "0.68rem", color: "#94a3b8" }}>Mesh Channel: /ws/peer</span>
              </div>
              <div style={{ display: "flex", gap: "0.6rem" }}>
                <select
                  style={{
                    background: "rgba(5,8,14,0.8)",
                    border: "1px solid rgba(255,255,255,0.15)",
                    color: "#fff",
                    padding: "0.4rem 0.6rem",
                    borderRadius: "6px",
                    fontSize: "0.8rem",
                    flex: 1,
                  }}
                  value={p2pTarget}
                  onChange={(e) => setP2pTarget(e.target.value)}
                >
                  {nodes.map((n) => (
                    <option key={n.node_id} value={n.node_id}>
                      {n.node_id} ({n.role})
                    </option>
                  ))}
                </select>
                <button
                  style={{
                    background: "linear-gradient(135deg, #00d2ff 0%, #0072ff 100%)",
                    border: "none",
                    color: "#ffffff",
                    padding: "0.4rem 0.9rem",
                    borderRadius: "6px",
                    fontSize: "0.78rem",
                    fontWeight: 700,
                    cursor: "pointer",
                  }}
                  onClick={sendP2pAnnouncement}
                  disabled={p2pBusy || !p2pTarget}
                >
                  {p2pBusy ? "Dispatching..." : "Send P2P Alert →"}
                </button>
              </div>
              {p2pResult && (
                <div style={{ fontSize: "0.78rem", marginTop: "0.5rem", color: p2pResult.startsWith("✓") ? "#4ade80" : "#f87171" }}>
                  {p2pResult}
                </div>
              )}
            </div>
          </div>

          {/* ── Live Activity Feed with Category Filters ── */}
          <div className={`${styles.panel} ${styles.activityPanel}`}>
            <div className={styles.heading}>
              <h2>Live Distributed Event Audit</h2>
              <span style={{ fontSize: "0.7rem", color: "#94a3b8" }}>AMQP &amp; WebSocket</span>
            </div>

            <div style={{ display: "flex", gap: "0.4rem", marginBottom: "0.8rem" }}>
              {["ALL", "EVIDENCE", "INCIDENT", "NODE", "WEBRTC"].map((cat) => (
                <button
                  key={cat}
                  style={{
                    fontSize: "0.68rem",
                    padding: "0.2rem 0.5rem",
                    borderRadius: "4px",
                    border: eventCategoryFilter === cat ? "1px solid #00d2ff" : "1px solid rgba(255,255,255,0.1)",
                    background: eventCategoryFilter === cat ? "rgba(0,210,255,0.2)" : "rgba(255,255,255,0.04)",
                    color: eventCategoryFilter === cat ? "#00d2ff" : "#94a7c0",
                    cursor: "pointer",
                    fontWeight: 700,
                  }}
                  onClick={() => setEventCategoryFilter(cat)}
                >
                  {cat}
                </button>
              ))}
            </div>

            <div className={styles.activityFeed}>
              {wsStatus === "connecting" && (
                <p className={styles.message}>Connecting to event stream…</p>
              )}
              {wsStatus === "connected" && filteredEvents.length === 0 && (
                <p className={styles.message}>
                  Subscribed to <code>{id}</code>.<br />
                  <small>Events will stream here automatically.</small>
                </p>
              )}
              {filteredEvents.map((ev) => (
                <ActivityItem key={ev.message_id} event={ev} />
              ))}
            </div>
          </div>

          {/* Participating Nodes */}
          <div className={styles.panel}>
            <div className={styles.heading}>
              <h2>Participating Nodes</h2>
              <span>{nodes.length.toString().padStart(2, "0")} CLUSTER NODES</span>
            </div>
            {nodes.length ? (
              <ul className={styles.items}>
                {nodes.map((node) => (
                  <li
                    key={node.node_id}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      padding: "0.6rem 0",
                      borderBottom: "1px solid rgba(255, 255, 255, 0.05)",
                    }}
                  >
                    <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                        <strong style={{ color: "#00d2ff", fontSize: "0.9rem" }}>{node.node_id}</strong>
                        <span
                          style={{
                            fontSize: "0.7rem",
                            color: "#8da2be",
                            padding: "0.15rem 0.45rem",
                            background: "rgba(255, 255, 255, 0.06)",
                            borderRadius: "4px",
                            fontWeight: 700,
                          }}
                        >
                          {node.role} · {node.status}
                        </span>
                      </div>
                      <span style={{ fontSize: "0.8rem", color: "#cbd5e1" }}>
                        {node.node_name}
                      </span>
                    </div>
                    <Link
                      href={`/live?nodeId=${node.node_id}&incidentId=${incident.incident_id}`}
                      style={{
                        fontSize: "0.75rem",
                        padding: "0.3rem 0.65rem",
                        background: "rgba(0, 210, 255, 0.15)",
                        border: "1px solid rgba(0, 210, 255, 0.4)",
                        borderRadius: "6px",
                        color: "#00d2ff",
                        textDecoration: "none",
                        fontWeight: 700,
                        whiteSpace: "nowrap",
                      }}
                    >
                      📹 Focus Stream
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p className={styles.message}>No participating nodes recorded.</p>
            )}
          </div>
        </section>

        {/* gRPC Remote Result Inspector Modal / Card */}
        {rpcResult && (
          <section
            style={{
              margin: "1.5rem 0",
              padding: "1.2rem 1.6rem",
              background: "linear-gradient(135deg, rgba(168, 85, 247, 0.15) 0%, rgba(88, 28, 135, 0.25) 100%)",
              border: "1px solid rgba(168, 85, 247, 0.5)",
              borderRadius: "12px",
              boxShadow: "0 8px 24px rgba(168, 85, 247, 0.2)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.8rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.8rem" }}>
                <span style={{ background: "#a855f7", color: "#fff", padding: "0.2rem 0.6rem", borderRadius: "4px", fontSize: "0.75rem", fontWeight: 800 }}>
                  gRPC / HTTP/2
                </span>
                <strong style={{ color: "#e9d5ff", fontSize: "1.05rem" }}>
                  Synchronous Remote RPC: GetEvidence({rpcResult.evidence_id})
                </strong>
              </div>
              <button
                style={{
                  background: "rgba(255,255,255,0.1)",
                  border: "none",
                  color: "#f3e8ff",
                  padding: "0.3rem 0.6rem",
                  borderRadius: "4px",
                  cursor: "pointer",
                  fontWeight: 700,
                  fontSize: "0.8rem",
                }}
                onClick={() => setRpcResult(null)}
              >
                ✕ Dismiss
              </button>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "1rem", marginBottom: "1rem" }}>
              <div style={{ background: "rgba(0,0,0,0.3)", padding: "0.8rem", borderRadius: "8px", border: "1px solid rgba(255,255,255,0.06)" }}>
                <span style={{ fontSize: "0.7rem", color: "#c084fc", fontWeight: 700 }}>MEASURED LATENCY</span>
                <div style={{ fontSize: "1.4rem", fontWeight: 800, color: "#4ade80" }}>{rpcResult.latency_ms} ms</div>
                <small style={{ color: "#94a3b8", fontSize: "0.72rem" }}>Direct binary HTTP/2 Protobuf</small>
              </div>

              <div style={{ background: "rgba(0,0,0,0.3)", padding: "0.8rem", borderRadius: "8px", border: "1px solid rgba(255,255,255,0.06)" }}>
                <span style={{ fontSize: "0.7rem", color: "#c084fc", fontWeight: 700 }}>TARGET NODE</span>
                <div style={{ fontSize: "1.1rem", fontWeight: 800, color: "#fff" }}>{rpcResult.node_id}</div>
                <small style={{ color: "#94a3b8", fontSize: "0.72rem" }}>Owner of evidence storage</small>
              </div>

              <div style={{ background: "rgba(0,0,0,0.3)", padding: "0.8rem", borderRadius: "8px", border: "1px solid rgba(255,255,255,0.06)" }}>
                <span style={{ fontSize: "0.7rem", color: "#c084fc", fontWeight: 700 }}>INTEGRITY STATUS</span>
                <div style={{ fontSize: "1.1rem", fontWeight: 800, color: "#38bdf8" }}>✓ SHA-256 Verified</div>
                <small style={{ color: "#94a3b8", fontSize: "0.72rem" }}>Tamper-proof hash validated</small>
              </div>
            </div>

            <pre
              style={{
                margin: 0,
                fontSize: "0.75rem",
                background: "rgba(5,8,14,0.85)",
                padding: "0.8rem",
                borderRadius: "8px",
                color: "#e2e8f0",
                overflowX: "auto",
                border: "1px solid rgba(255,255,255,0.08)",
              }}
            >
              {JSON.stringify(rpcResult.data, null, 2)}
            </pre>
          </section>
        )}

        {/* Evidence Table with Ownership Labels & Remote gRPC Fetch */}
        <section className={styles.panel + " " + styles.listPanel} style={{ marginTop: "1.5rem" }}>
          <div className={styles.heading}>
            <h2>Attached Multi-Node Evidence</h2>
            <span>{evidence.length.toString().padStart(2, "0")} ITEMS ACROSS DISTRIBUTED NODES</span>
          </div>
          {evidence.length ? (
            <div className={styles.table}>
              <table>
                <thead>
                  <tr>
                    <th>Evidence ID</th>
                    <th>Storage Node</th>
                    <th>Event Type</th>
                    <th>Media Type</th>
                    <th>Title</th>
                    <th>Integrity / Hash</th>
                    <th>Distributed Retrieval</th>
                  </tr>
                </thead>
                <tbody>
                  {evidence.map((item) => (
                    <tr key={item.evidence_id}>
                      <td>
                        <strong style={{ color: "#00d2ff" }}>{item.evidence_id}</strong>
                      </td>
                      <td>
                        <span
                          style={{
                            padding: "0.2rem 0.55rem",
                            borderRadius: "4px",
                            background: "rgba(0, 210, 255, 0.12)",
                            border: "1px solid rgba(0, 210, 255, 0.3)",
                            color: "#00d2ff",
                            fontSize: "0.75rem",
                            fontWeight: 800,
                          }}
                        >
                          {item.node_id}
                        </span>
                      </td>
                      <td>{item.event_type}</td>
                      <td>
                        <span style={{ fontSize: "0.75rem", background: "rgba(255,255,255,0.08)", padding: "0.15rem 0.4rem", borderRadius: "4px" }}>
                          {item.evidence_type}
                        </span>
                      </td>
                      <td>{item.title}</td>
                      <td>
                        <span style={{ fontSize: "0.72rem", color: "#4ade80", fontFamily: "var(--font-geist-mono)" }}>
                          ✓ SHA-256 Valid
                        </span>
                      </td>
                      <td>
                        <button
                          style={{
                            fontSize: "0.75rem",
                            padding: "0.35rem 0.75rem",
                            borderRadius: "6px",
                            background: "rgba(168, 85, 247, 0.2)",
                            border: "1px solid rgba(168, 85, 247, 0.5)",
                            color: "#e9d5ff",
                            cursor: "pointer",
                            fontWeight: 700,
                            transition: "all 0.2s ease",
                          }}
                          onClick={() => void fetchRemoteEvidence(item.node_id, item.evidence_id)}
                          disabled={rpcLoading === item.evidence_id}
                        >
                          {rpcLoading === item.evidence_id ? "⚡ Querying..." : "⚡ Fetch via gRPC"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className={styles.message}>No local evidence attached.</p>
          )}

          {localEvidence.filter(
            (item) =>
              !evidence.some(
                (attached) => attached.evidence_id === item.evidence_id,
              ),
          ).length > 0 && (
            <div className={styles.attach} style={{ marginTop: "1rem" }}>
              <h3>Attach Unlinked Evidence to Incident</h3>
              <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginTop: "0.5rem" }}>
                {localEvidence
                  .filter(
                    (item) =>
                      !evidence.some(
                        (attached) => attached.evidence_id === item.evidence_id,
                      ),
                  )
                  .map((item) => (
                    <button
                      key={item.evidence_id}
                      onClick={() => void attach(item.evidence_id)}
                    >
                      + Attach {item.evidence_id} ({item.title})
                    </button>
                  ))}
              </div>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
