"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import HeaderNav from "../../components/HeaderNav";
import { useEventStream, type WsEvent } from "../../hooks/useEventStream";
import styles from "./page.module.css";

const API = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
const INCIDENT_ID = "INC-000001";

type NodeSummary = {
  node_id: string;
  node_name: string;
  node_type: string;
  status: string;
};
type Peer = {
  node_id: string;
  connection_state: string;
  rtt_ms: number | null;
};
type Health = {
  status: string;
  services: Record<string, string>;
  metrics: Record<string, number>;
};

const nodeIcon: Record<string, string> = {
  EVIDENCE: "📹",
  SECURITY: "🚨",
  MOBILE: "🛡️",
};
function timeOf(value: string) {
  return new Date(value).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}
function eventLabel(event: WsEvent) {
  const labels: Record<string, string> = {
    "evidence.created": "Evidence captured",
    "incident.created": "Incident opened",
    "node.status_changed": "Node status changed",
    "webrtc.session_created": "Live stream negotiated",
    "p2p.message_sent": "Direct peer message",
  };
  return labels[event.event_type] ?? event.event_type.replaceAll(".", " · ");
}

export default function DashboardPage() {
  const [nodes, setNodes] = useState<NodeSummary[]>([]);
  const [peers, setPeers] = useState<Peer[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<{
    text: string;
    error?: boolean;
  } | null>(null);
  const [selectedNode, setSelectedNode] = useState("CCTV-B");
  const { status: streamStatus, events } = useEventStream({ maxEvents: 80 });

  const load = useCallback(async () => {
    try {
      const [healthResponse, nodesResponse, peersResponse] = await Promise.all([
        fetch(`${API}/health`),
        fetch(`${API}/api/v1/nodes`),
        fetch(`${API}/api/v1/peers`),
      ]);
      if (healthResponse.ok) setHealth(await healthResponse.json());
      if (nodesResponse.ok) setNodes(await nodesResponse.json());
      if (peersResponse.ok) setPeers(await peersResponse.json());
    } catch {
      setNotice({
        text: "Coordinator is unreachable. Start the Docker stack to see live telemetry.",
        error: true,
      });
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
    const timer = setInterval(() => void load(), 3000);
    return () => clearInterval(timer);
  }, [load]);
  const onlineCount = nodes.filter((node) => node.status === "ONLINE").length;
  const latestEvents = useMemo(() => events.slice(0, 8), [events]);

  async function post(path: string, body?: object) {
    const response = await fetch(`${API}${path}`, {
      method: "POST",
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || "The operation failed.");
    return data;
  }

  async function triggerDetection() {
    setBusy("detect");
    setNotice(null);
    try {
      await post("/api/v1/demo/simulate/event", {
        event_type: "incident.created",
        incident_id: INCIDENT_ID,
        payload: {
          source: "SECURITY-A",
          location: "North Gate",
          reason: "IR tripwire crossed",
          severity: "HIGH",
        },
      });
      setNotice({
        text: "Detection published: SECURITY-A → RabbitMQ → every subscribed node and this dashboard.",
      });
    } catch (error) {
      setNotice({
        text: error instanceof Error ? error.message : "Detection failed",
        error: true,
      });
    } finally {
      setBusy(null);
    }
  }
  async function sendPeerAlert() {
    setBusy("p2p");
    setNotice(null);
    try {
      const result = await post(
        `/api/v1/peers/${selectedNode}/announce/incident/${INCIDENT_ID}`,
      );
      setNotice({
        text: `Direct P2P alert delivered to ${selectedNode}. Message ${result.message_id ?? "accepted"}; broker bypassed.`,
      });
      await load();
    } catch (error) {
      setNotice({
        text: error instanceof Error ? error.message : "P2P alert failed",
        error: true,
      });
    } finally {
      setBusy(null);
    }
  }
  async function simulateOutage() {
    setBusy("outage");
    setNotice(null);
    try {
      await post("/api/v1/demo/simulate/node-status", {
        node_id: selectedNode,
        status: "OFFLINE",
      });
      setNotice({
        text: `${selectedNode} is logically offline. Watch the event stream: other nodes and the broker remain available.`,
      });
      await load();
    } catch (error) {
      setNotice({
        text:
          error instanceof Error ? error.message : "Fault simulation failed",
        error: true,
      });
    } finally {
      setBusy(null);
    }
  }
  async function resetDemo() {
    setBusy("reset");
    setNotice(null);
    try {
      await post("/api/v1/demo/reset");
      setNotice({
        text: "Demo reset complete. Four canonical nodes and the shared incident are ready.",
      });
      await load();
    } catch (error) {
      setNotice({
        text: error instanceof Error ? error.message : "Reset failed",
        error: true,
      });
    } finally {
      setBusy(null);
    }
  }

  return (
    <main className={styles.page}>
      <HeaderNav />
      <div className={styles.shell}>
        <section className={styles.hero}>
          <div>
            <div className={styles.eyebrow}>
              <span className={styles.liveDot} /> LIVE INCIDENT ROOM · SECTOR 4
              NORTH GATE
            </div>
            <h1>What happens when one camera sees a breach?</h1>
            <p>
              Follow one security event as it travels through independent nodes,
              the message broker, direct peer links, and the investigator
              dashboard.
            </p>
          </div>
          <div className={styles.heroActions}>
            <button
              className={styles.primaryButton}
              onClick={triggerDetection}
              disabled={busy !== null}
            >
              {busy === "detect" ? "Publishing…" : "🚨 Trigger detection"}
            </button>
            <Link
              href={`/incidents/${INCIDENT_ID}`}
              className={styles.secondaryButton}
            >
              Open incident brief →
            </Link>
          </div>
        </section>
        {notice && (
          <div
            className={`${styles.notice} ${notice.error ? styles.noticeError : ""}`}
          >
            {notice.error ? "⚠" : "✓"} {notice.text}
          </div>
        )}
        <section className={styles.metrics}>
          <div>
            <span>Nodes online</span>
            <strong>
              {onlineCount || "—"}
              <small> / {nodes.length || 4}</small>
            </strong>
            <em
              className={
                onlineCount === nodes.length ? styles.good : styles.warn
              }
            >
              {onlineCount === nodes.length ? "All responding" : "Degraded"}
            </em>
          </div>
          <div>
            <span>Event stream</span>
            <strong>{streamStatus === "connected" ? "LIVE" : "—"}</strong>
            <em
              className={
                streamStatus === "connected" ? styles.good : styles.warn
              }
            >
              {streamStatus === "connected"
                ? "WebSocket subscribed"
                : streamStatus}
            </em>
          </div>
          <div>
            <span>Messages observed</span>
            <strong>{events.length}</strong>
            <em>Last 80 in browser</em>
          </div>
          <div>
            <span>System health</span>
            <strong>{health?.status?.toUpperCase() ?? "—"}</strong>
            <em>{health?.services?.rabbitmq ?? "Waiting for coordinator"}</em>
          </div>
        </section>
        <div className={styles.mainGrid}>
          <section className={styles.panel}>
            <div className={styles.panelHeading}>
              <div>
                <span className={styles.sectionKicker}>01 · OBSERVE</span>
                <h2>Distributed scene map</h2>
              </div>
              <span className={styles.connectionLegend}>
                <i className={styles.onlineLegend} /> live node{" "}
                <i className={styles.linkLegend} /> P2P link
              </span>
            </div>
            <div className={styles.map}>
              <div className={styles.mapLane}>
                {nodes.map((node) => {
                  const peer = peers.find(
                    (item) => item.node_id === node.node_id,
                  );
                  const offline = node.status !== "ONLINE";
                  return (
                    <button
                      key={node.node_id}
                      className={`${styles.nodeCard} ${offline ? styles.nodeOffline : ""} ${selectedNode === node.node_id ? styles.nodeSelected : ""}`}
                      onClick={() => setSelectedNode(node.node_id)}
                    >
                      <span className={styles.nodeIcon}>
                        {nodeIcon[node.node_type] ?? "🖥️"}
                      </span>
                      <span className={styles.nodeCopy}>
                        <b>{node.node_id}</b>
                        <small>{node.node_name}</small>
                        <small>
                          {offline
                            ? "OFFLINE · simulated"
                            : `${node.node_type} · ${peer?.connection_state === "CONNECTED" ? `${peer.rtt_ms ?? "—"} ms P2P` : "ready"}`}
                        </small>
                      </span>
                      <i
                        className={
                          offline ? styles.offlineDot : styles.onlineDot
                        }
                      />
                    </button>
                  );
                })}
                {!nodes.length && (
                  <div className={styles.emptyMap}>
                    Waiting for node registry…
                    <br />
                    <small>
                      Use Diagnostics → Re-seed if this is a new environment.
                    </small>
                  </div>
                )}
              </div>
              <div className={styles.bus}>
                <span>📨</span>
                <div>
                  <b>RabbitMQ event bus</b>
                  <small>echovault.events · durable async fan-out</small>
                </div>
                <strong>AMQP</strong>
              </div>
              <div className={styles.route}>
                <span>SECURITY-A</span>
                <div className={styles.routeLine}>
                  <i /> <b>event travels here</b> <i />
                </div>
                <span>Dashboard subscribers</span>
              </div>
            </div>
            <div className={styles.mapCaption}>
              <b>Why this is distributed:</b> CCTV-A can continue capturing
              while CCTV-B is unavailable. The broker decouples publishers from
              consumers; the direct P2P route is reserved for urgent
              node-to-node control.
            </div>
          </section>
          <section className={styles.panel}>
            <div className={styles.panelHeading}>
              <div>
                <span className={styles.sectionKicker}>02 · ACT</span>
                <h2>Operator controls</h2>
              </div>
              <span className={styles.protocolBadge}>INVESTIGATOR TOOLS</span>
            </div>
            <div className={styles.controlStack}>
              <div className={styles.control}>
                <div>
                  <b>Record a new observation</b>
                  <small>
                    Share a verified detection with every connected source and
                    keep the case timeline current.
                  </small>
                </div>
                <button onClick={triggerDetection} disabled={busy !== null}>
                  {busy === "detect" ? "Saving…" : "Record observation"}
                </button>
              </div>
              <div className={styles.control}>
                <div>
                  <b>Contact a field source</b>
                  <small>
                    Send an urgent instruction directly to a selected camera or
                    patrol source.
                  </small>
                </div>
                <select
                  value={selectedNode}
                  onChange={(event) => setSelectedNode(event.target.value)}
                >
                  {nodes
                    .filter((node) => node.node_id !== "SECURITY-A")
                    .map((node) => (
                      <option key={node.node_id}>{node.node_id}</option>
                    ))}
                </select>
                <button onClick={sendPeerAlert} disabled={busy !== null}>
                  {busy === "p2p" ? "Sending…" : "Send instruction"}
                </button>
              </div>
              <div className={styles.control}>
                <div>
                  <b>Check source availability</b>
                  <small>
                    Simulate a source going offline and confirm the rest of the
                    investigation remains operational.
                  </small>
                </div>
                <button
                  className={styles.dangerButton}
                  onClick={simulateOutage}
                  disabled={busy !== null}
                >
                  {busy === "outage" ? "Checking…" : `Test ${selectedNode}`}
                </button>
              </div>
            </div>
            <div className={styles.controlFooter}>
              <span>Workspace maintenance</span>
              <button onClick={resetDemo} disabled={busy !== null}>
                {busy === "reset" ? "Restoring…" : "Restore sample workspace"}
              </button>
            </div>
          </section>
        </div>
        <div className={styles.bottomGrid}>
          <section className={styles.panel}>
            <div className={styles.panelHeading}>
              <div>
                <span className={styles.sectionKicker}>03 · INVESTIGATE</span>
                <h2>What is happening now</h2>
              </div>
              <span className={styles.streamState}>
                <i
                  className={
                    streamStatus === "connected"
                      ? styles.onlineDot
                      : styles.offlineDot
                  }
                />{" "}
                {streamStatus}
              </span>
            </div>
            <div className={styles.timeline}>
              {latestEvents.length ? (
                latestEvents.map((event) => (
                  <div className={styles.timelineItem} key={event.message_id}>
                    <span className={styles.timelineTime}>
                      {timeOf(event.timestamp)}
                    </span>
                    <span className={styles.timelineDot} />
                    <div>
                      <b>{eventLabel(event)}</b>
                      <small>
                        {event.source_node_id} <span>→</span>{" "}
                        {event.incident_id ?? "cluster"} ·{" "}
                        <code>{event.event_type}</code>
                      </small>
                    </div>
                  </div>
                ))
              ) : (
                <div className={styles.emptyTimeline}>
                  No activity yet. Record an observation to begin the case
                  timeline.
                </div>
              )}
            </div>
          </section>
          <section className={styles.panel}>
            <div className={styles.panelHeading}>
              <div>
                <span className={styles.sectionKicker}>CASE CONTEXT</span>
                <h2>How EchoVault protects the investigation</h2>
              </div>
            </div>
            <div className={styles.teachingCard}>
              <div className={styles.quote}>
                “Every observation stays traceable to its source.”
              </div>
              <p>
                When a source detects a breach, EchoVault preserves who saw it,
                when it happened, and how it reached the case. Investigators can
                follow the activity live without moving original evidence into
                one central folder.
              </p>
              <div className={styles.teachingRows}>
                <span>
                  <b>Source</b> original observation
                </span>
                <span>
                  <b>Audit</b> traceable activity
                </span>
                <span>
                  <b>Evidence</b> verified ownership
                </span>
                <span>
                  <b>Response</b> direct instructions
                </span>
                <span>
                  <b>Live view</b> immediate context
                </span>
              </div>
            </div>
            <Link href="/messaging" className={styles.textLink}>
              Inspect the full message ledger →
            </Link>
          </section>
        </div>
      </div>
    </main>
  );
}
