"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import HeaderNav from "../../components/HeaderNav";
import styles from "./page.module.css";

// ── Types ────────────────────────────────────────────────────────────────────

type PeerStatus = {
  node_id: string;
  node_name: string;
  node_type: string;
  host: string;
  port: number;
  p2p_host: string;
  p2p_port: number;
  connection_state: "CONNECTED" | "CONNECTING" | "DISCONNECTED" | "HANDSHAKING" | "DISCONNECTING";
  connected_at: string | null;
  last_seen_at: string | null;
  rtt_ms: number | null;
  reconnect_attempts: number;
  is_outbound: boolean;
};

type PeerMessageRecord = {
  id: string;
  message_id: string;
  source_node_id: string;
  target_node_id: string;
  message_type: string;
  received_at: string;
  processed_at: string | null;
  status: "RECEIVED" | "PROCESSED" | "FAILED" | "IGNORED";
  error_message: string | null;
  payload: Record<string, unknown> | null;
};

type P2PHealth = {
  service: string;
  status: string;
  connected_peers: number;
};

type EvidenceItem = {
  evidence_id: string;
  title: string;
};

type IncidentItem = {
  incident_id: string;
  title: string;
};

const backendUrl =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

const MESSAGE_TYPES = [
  "PEER_MESSAGE",
  "EVIDENCE_ANNOUNCEMENT",
  "INCIDENT_ANNOUNCEMENT",
  "PING",
  "PONG",
  "HANDSHAKE",
];

// ── Helper Components ─────────────────────────────────────────────────────────

function StateBadge({ state }: { state: PeerStatus["connection_state"] }) {
  const cls =
    state === "CONNECTED"
      ? styles.badgeConnected
      : state === "CONNECTING" || state === "HANDSHAKING"
      ? styles.badgeConnecting
      : styles.badgeDisconnected;
  return <span className={`${styles.badge} ${cls}`}>{state}</span>;
}

function StatusBadge({ status }: { status: PeerMessageRecord["status"] }) {
  const cls =
    status === "PROCESSED"
      ? styles.badgeProcessed
      : status === "FAILED"
      ? styles.badgeFailed
      : status === "IGNORED"
      ? styles.badgeIgnored
      : styles.badgeReceived;
  return <span className={`${styles.badge} ${cls}`}>{status}</span>;
}

function TypeChip({ type }: { type: string }) {
  return <span className={styles.typeChip}>{type}</span>;
}

function relative(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const secs = Math.floor(diff / 1000);
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  return new Date(iso).toLocaleTimeString();
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function PeersPage() {
  const [peers, setPeers] = useState<PeerStatus[]>([]);
  const [messages, setMessages] = useState<PeerMessageRecord[]>([]);
  const [evidenceList, setEvidenceList] = useState<EvidenceItem[]>([]);
  const [incidentList, setIncidentList] = useState<IncidentItem[]>([]);
  const [p2pHealth, setP2pHealth] = useState<P2PHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Direct Messaging Form State
  const [targetPeer, setTargetPeer] = useState("");
  const [directMsg, setDirectMsg] = useState("Direct telemetry check from peer");
  const [msgResult, setMsgResult] = useState<string | null>(null);
  const [msgBusy, setMsgBusy] = useState(false);

  // Ping State
  const [pingingNode, setPingingNode] = useState<string | null>(null);
  const [pingResult, setPingResult] = useState<Record<string, string>>({});

  // Announcement States
  const [announceEvPeer, setAnnounceEvPeer] = useState("");
  const [selectedEvId, setSelectedEvId] = useState("");
  const [announceEvResult, setAnnounceEvResult] = useState<string | null>(null);

  const [announceIncPeer, setAnnounceIncPeer] = useState("");
  const [selectedIncId, setSelectedIncId] = useState("");
  const [announceIncResult, setAnnounceIncResult] = useState<string | null>(null);

  // Filter state for messages table
  const [filterType, setFilterType] = useState("");
  const [filterSource, setFilterSource] = useState("");
  const [filterStatus, setFilterStatus] = useState("");

  // ── Data Loader ─────────────────────────────────────────────────────────────
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const msgParams = new URLSearchParams();
      if (filterType) msgParams.set("message_type", filterType);
      if (filterSource) msgParams.set("source_node_id", filterSource);
      if (filterStatus) msgParams.set("status", filterStatus);

      const [peersRes, msgsRes, healthRes, evRes, incRes] = await Promise.all([
        fetch(`${backendUrl}/api/v1/peers`),
        fetch(`${backendUrl}/api/v1/peers/messages?${msgParams}`),
        fetch(`${backendUrl}/health/p2p`).catch(() => null),
        fetch(`${backendUrl}/api/v1/evidence`).catch(() => null),
        fetch(`${backendUrl}/api/v1/incidents`).catch(() => null),
      ]);

      if (!peersRes.ok) throw new Error("Failed to load peers from node registry");
      const peersData: PeerStatus[] = await peersRes.json();
      setPeers(peersData);

      if (msgsRes.ok) {
        setMessages(await msgsRes.json());
      }

      if (healthRes && healthRes.ok) {
        setP2pHealth(await healthRes.json());
      }

      if (evRes && evRes.ok) {
        const evs = await evRes.json();
        setEvidenceList(evs.map((e: { evidence_id: string; title: string }) => ({ evidence_id: e.evidence_id, title: e.title })));
      }

      if (incRes && incRes.ok) {
        const incs = await incRes.json();
        setIncidentList(incs.map((i: { incident_id: string; title: string }) => ({ incident_id: i.incident_id, title: i.title })));
      }

      // Default target peer if not set
      if (!targetPeer && peersData.length > 0) {
        setTargetPeer(peersData[0].node_id);
        setAnnounceEvPeer(peersData[0].node_id);
        setAnnounceIncPeer(peersData[0].node_id);
      }

      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [filterType, filterSource, filterStatus, targetPeer]);

  useEffect(() => {
    void load();
    const interval = setInterval(() => void load(), 4000);
    return () => clearInterval(interval);
  }, [load]);

  // ── Actions ─────────────────────────────────────────────────────────────────

  async function handleConnect(nodeId: string) {
    try {
      const res = await fetch(`${backendUrl}/api/v1/peers/${nodeId}/connect`, {
        method: "POST",
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) throw new Error(data?.detail || "Failed to establish direct P2P connection");
      await load();
    } catch (err) {
      alert(`Connect error: ${err instanceof Error ? err.message : "Failed"}`);
    }
  }

  async function handleDisconnect(nodeId: string) {
    try {
      await fetch(`${backendUrl}/api/v1/peers/${nodeId}/disconnect`, {
        method: "POST",
      });
      await load();
    } catch (err) {
      alert(`Disconnect error: ${err instanceof Error ? err.message : "Failed"}`);
    }
  }

  async function handlePing(nodeId: string) {
    setPingingNode(nodeId);
    try {
      const res = await fetch(`${backendUrl}/api/v1/peers/${nodeId}/ping`, {
        method: "POST",
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Ping failed");
      setPingResult((prev) => ({
        ...prev,
        [nodeId]: `${data.rtt_ms} ms (Direct RTT)`,
      }));
      await load();
    } catch (err) {
      setPingResult((prev) => ({
        ...prev,
        [nodeId]: `Err: ${err instanceof Error ? err.message : "Failed"}`,
      }));
    } finally {
      setPingingNode(null);
    }
  }

  async function handleSendDirectMessage() {
    if (!targetPeer) return;
    setMsgBusy(true);
    setMsgResult(null);
    try {
      const res = await fetch(`${backendUrl}/api/v1/peers/${targetPeer}/message`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: directMsg,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Direct message transmission failed");
      setMsgResult(`✓ Direct point-to-point delivery to ${targetPeer} succeeded (ID: ${data.message_id})`);
      await load();
    } catch (err) {
      setMsgResult(`✗ Error: ${err instanceof Error ? err.message : "Failed"}`);
    } finally {
      setMsgBusy(false);
    }
  }

  async function handleAnnounceEvidence() {
    if (!announceEvPeer || !selectedEvId) return;
    setAnnounceEvResult(null);
    try {
      const res = await fetch(
        `${backendUrl}/api/v1/peers/${announceEvPeer}/announce/evidence/${selectedEvId}`,
        { method: "POST" }
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Announcement failed");
      setAnnounceEvResult(`✓ Announced ${selectedEvId} directly to ${announceEvPeer}`);
      await load();
    } catch (err) {
      setAnnounceEvResult(`✗ ${err instanceof Error ? err.message : "Failed"}`);
    }
  }

  async function handleAnnounceIncident() {
    if (!announceIncPeer || !selectedIncId) return;
    setAnnounceIncResult(null);
    try {
      const res = await fetch(
        `${backendUrl}/api/v1/peers/${announceIncPeer}/announce/incident/${selectedIncId}`,
        { method: "POST" }
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Announcement failed");
      setAnnounceIncResult(`✓ Announced ${selectedIncId} directly to ${announceIncPeer}`);
      await load();
    } catch (err) {
      setAnnounceIncResult(`✗ ${err instanceof Error ? err.message : "Failed"}`);
    }
  }

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <main className={styles.page}>
      <HeaderNav />

      {/* ── Hero ── */}
      <section className={styles.hero}>
        <p className={styles.kicker}>DIRECT NODE-TO-NODE MESH</p>
        <h1>Peer-to-Peer Communication</h1>
        <p className={styles.sub}>
          Direct point-to-point <code>/ws/peer</code> channels between EchoVault nodes.
          Messages travel directly between peer endpoints without broker or registry mediation.
        </p>

        {/* Status Row */}
        <div className={styles.statusRow}>
          <div className={styles.statusItem}>
            <span className={styles.healthLabel}>P2P Mesh</span>
            <span className={`${styles.healthDot} ${styles.dotHealthy}`} />
            <span className={styles.healthStatus}>
              {p2pHealth?.status ?? "active"}
            </span>
          </div>
          <div className={styles.statusDivider} />
          <div className={styles.statusItem}>
            <span className={styles.healthLabel}>Active Peers</span>
            <span className={styles.healthStatus}>
              {p2pHealth?.connected_peers ?? 0} connected
            </span>
          </div>
          <button className={styles.refreshBtn} onClick={() => void load()}>
            ↺ Refresh state
          </button>
        </div>
      </section>

      {/* ── Architecture Comparison Banner ── */}
      <section className={styles.archBanner}>
        <div className={styles.archItem}>
          <span className={styles.archIcon}>⚡</span>
          <div>
            <strong>gRPC (Part 5)</strong>
            <p>Sync RPC: Node A requests immediate answer from Node B</p>
          </div>
        </div>
        <div className={styles.archDivider}>vs</div>
        <div className={styles.archItem}>
          <span className={styles.archIcon}>📨</span>
          <div>
            <strong>RabbitMQ (Part 6)</strong>
            <p>Async Pub/Sub: Broker routes 1-to-N decoupled events</p>
          </div>
        </div>
        <div className={styles.archDivider}>vs</div>
        <div className={styles.archItem}>
          <span className={styles.archIcon}>⚡🌊</span>
          <div>
            <strong>WebSocket (Part 7)</strong>
            <p>Stream: Backend pushes real-time events to Browser</p>
          </div>
        </div>
        <div className={styles.archDivider}>vs</div>
        <div className={`${styles.archItem} ${styles.archItemActive}`}>
          <span className={styles.archIcon}>🌐</span>
          <div>
            <strong>Direct P2P (Part 8)</strong>
            <p>Mesh: Direct point-to-point connection between nodes</p>
          </div>
        </div>
      </section>

      {error && <div className={styles.errorBanner}>{error}</div>}

      {/* ── Discovered Peers Table ── */}
      <section className={styles.sectionWrap}>
        <div className={styles.sectionHeader}>
          <h2>Discovered Peers from Registry</h2>
          <span className={styles.count}>{peers.length} nodes</span>
        </div>

        {loading && peers.length === 0 ? (
          <div className={styles.state}>Loading peer network…</div>
        ) : peers.length === 0 ? (
          <div className={styles.state}>
            No remote nodes registered. Register additional nodes to establish P2P links.
          </div>
        ) : (
          <div className={styles.tableWrap}>
            <table>
              <thead>
                <tr>
                  <th>Peer Node</th>
                  <th>Type</th>
                  <th>Direct Address</th>
                  <th>Status</th>
                  <th>Direct RTT</th>
                  <th>Last Seen</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {peers.map((peer) => (
                  <tr key={peer.node_id}>
                    <td>
                      <strong>{peer.node_id}</strong>
                      <small className={styles.subText}>{peer.node_name}</small>
                    </td>
                    <td><span className={styles.typeTag}>{peer.node_type}</span></td>
                    <td className={styles.monoCell}>
                      ws://{peer.p2p_host}:{peer.p2p_port}/ws/peer
                    </td>
                    <td><StateBadge state={peer.connection_state} /></td>
                    <td>
                      {peer.rtt_ms !== null ? (
                        <span className={styles.rttTag}>{peer.rtt_ms} ms</span>
                      ) : (
                        <span className={styles.dimText}>—</span>
                      )}
                    </td>
                    <td>
                      {peer.last_seen_at ? relative(peer.last_seen_at) : "Never"}
                    </td>
                    <td>
                      <div className={styles.actionRow}>
                        {peer.connection_state === "CONNECTED" ? (
                          <>
                            <button
                              className={styles.pingBtn}
                              disabled={pingingNode === peer.node_id}
                              onClick={() => void handlePing(peer.node_id)}
                            >
                              {pingingNode === peer.node_id ? "Pinging…" : "Ping"}
                            </button>
                            <button
                              className={styles.disconnectBtn}
                              onClick={() => void handleDisconnect(peer.node_id)}
                            >
                              Disconnect
                            </button>
                          </>
                        ) : (
                          <button
                            className={styles.connectBtn}
                            onClick={() => void handleConnect(peer.node_id)}
                          >
                            Connect Direct Link
                          </button>
                        )}
                      </div>
                      {pingResult[peer.node_id] && (
                        <small className={styles.pingFeedback}>
                          {pingResult[peer.node_id]}
                        </small>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* ── Interactive Direct Communication Panels ── */}
      <div className={styles.gridPanels}>
        {/* Direct Text Message Panel */}
        <section className={styles.devPanel}>
          <div className={styles.panelTitle}>
            <span className={styles.devBadge}>DEV TEST</span>
            <h3>Direct Peer Message</h3>
            <p>Sends a direct payload over the established P2P WebSocket link without going through RabbitMQ.</p>
          </div>
          <div className={styles.formGroup}>
            <label>
              Target Connected Peer
              <select
                value={targetPeer}
                onChange={(e) => setTargetPeer(e.target.value)}
              >
                {peers.map((p) => (
                  <option key={p.node_id} value={p.node_id}>
                    {p.node_id} ({p.connection_state})
                  </option>
                ))}
              </select>
            </label>
            <label>
              Direct Message Payload
              <input
                value={directMsg}
                onChange={(e) => setDirectMsg(e.target.value)}
                placeholder="Message text..."
              />
            </label>
            <button
              className={styles.primaryActionBtn}
              disabled={msgBusy || !targetPeer}
              onClick={() => void handleSendDirectMessage()}
            >
              {msgBusy ? "Transmitting…" : "Send Direct P2P Message →"}
            </button>
          </div>
          {msgResult && (
            <p className={msgResult.startsWith("✓") ? styles.successMsg : styles.errorMsg}>
              {msgResult}
            </p>
          )}
        </section>

        {/* Targeted Announcement Panel */}
        <section className={styles.devPanel}>
          <div className={styles.panelTitle}>
            <span className={styles.devBadge}>TARGETED ANNOUNCEMENT</span>
            <h3>Direct Evidence &amp; Incident Announce</h3>
            <p>Announce metadata to a specific peer over point-to-point channel.</p>
          </div>

          <div className={styles.subForm}>
            <h4>Announce Evidence</h4>
            <div className={styles.inlineForm}>
              <select
                value={announceEvPeer}
                onChange={(e) => setAnnounceEvPeer(e.target.value)}
              >
                {peers.map((p) => (
                  <option key={p.node_id} value={p.node_id}>{p.node_id}</option>
                ))}
              </select>
              <select
                value={selectedEvId}
                onChange={(e) => setSelectedEvId(e.target.value)}
              >
                <option value="">Select Evidence...</option>
                {evidenceList.map((e) => (
                  <option key={e.evidence_id} value={e.evidence_id}>
                    {e.evidence_id} - {e.title}
                  </option>
                ))}
              </select>
              <button
                className={styles.secondaryBtn}
                disabled={!announceEvPeer || !selectedEvId}
                onClick={() => void handleAnnounceEvidence()}
              >
                Announce →
              </button>
            </div>
            {announceEvResult && (
              <p className={announceEvResult.startsWith("✓") ? styles.successMsg : styles.errorMsg}>
                {announceEvResult}
              </p>
            )}
          </div>

          <div className={styles.subForm} style={{ marginTop: "1rem" }}>
            <h4>Announce Incident</h4>
            <div className={styles.inlineForm}>
              <select
                value={announceIncPeer}
                onChange={(e) => setAnnounceIncPeer(e.target.value)}
              >
                {peers.map((p) => (
                  <option key={p.node_id} value={p.node_id}>{p.node_id}</option>
                ))}
              </select>
              <select
                value={selectedIncId}
                onChange={(e) => setSelectedIncId(e.target.value)}
              >
                <option value="">Select Incident...</option>
                {incidentList.map((i) => (
                  <option key={i.incident_id} value={i.incident_id}>
                    {i.incident_id} - {i.title}
                  </option>
                ))}
              </select>
              <button
                className={styles.secondaryBtn}
                disabled={!announceIncPeer || !selectedIncId}
                onClick={() => void handleAnnounceIncident()}
              >
                Announce →
              </button>
            </div>
            {announceIncResult && (
              <p className={announceIncResult.startsWith("✓") ? styles.successMsg : styles.errorMsg}>
                {announceIncResult}
              </p>
            )}
          </div>
        </section>
      </div>

      {/* ── Received P2P Messages (Idempotent Inbox) ── */}
      <section className={styles.sectionWrap}>
        <div className={styles.sectionHeader}>
          <div>
            <h2>Direct P2P Message Inbox &amp; Audit Log</h2>
            <p className={styles.subText}>
              Every received direct P2P frame is recorded in <code>peer_messages</code> for local auditing &amp; idempotency detection.
            </p>
          </div>
          <span className={styles.count}>{messages.length} messages</span>
        </div>

        {/* Filter Row */}
        <div className={styles.filterRow}>
          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
          >
            <option value="">All Message Types</option>
            {MESSAGE_TYPES.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
          <input
            placeholder="Filter Source Node (e.g. CCTV-A)"
            value={filterSource}
            onChange={(e) => setFilterSource(e.target.value)}
          />
          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
          >
            <option value="">All Statuses</option>
            <option value="PROCESSED">PROCESSED</option>
            <option value="IGNORED">IGNORED</option>
            <option value="FAILED">FAILED</option>
          </select>
        </div>

        {messages.length === 0 ? (
          <div className={styles.state}>
            No direct P2P messages received yet. Send a test message or announcement above.
          </div>
        ) : (
          <div className={styles.tableWrap}>
            <table>
              <thead>
                <tr>
                  <th>Message ID</th>
                  <th>Type</th>
                  <th>Source Peer</th>
                  <th>Received</th>
                  <th>Status</th>
                  <th>Payload Content</th>
                </tr>
              </thead>
              <tbody>
                {messages.map((m) => (
                  <tr key={m.id}>
                    <td className={styles.monoCell}>
                      <span title={m.message_id}>{m.message_id.slice(0, 16)}…</span>
                    </td>
                    <td><TypeChip type={m.message_type} /></td>
                    <td><strong>{m.source_node_id}</strong></td>
                    <td title={m.received_at}>{relative(m.received_at)}</td>
                    <td><StatusBadge status={m.status} /></td>
                    <td className={styles.payloadCell}>
                      <code>{JSON.stringify(m.payload)}</code>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
