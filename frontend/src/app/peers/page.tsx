"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";
import HeaderNav from "../../components/HeaderNav";
import styles from "./page.module.css";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

type Peer = {
  node_id: string;
  node_name: string;
  node_type: string;
  p2p_host: string | null;
  p2p_port: number | null;
  connection_state: string;
  rtt_ms: number | null;
  connected_at: string | null;
};

type InboxMessage = {
  id: string;
  message_id: string;
  source_node_id: string;
  target_node_id: string | null;
  message_type: string;
  received_at: string;
  status: string;
  error_message: string | null;
};

type EvidenceItem = { evidence_id: string; title: string; node_id: string };
type IncidentItem = { incident_id: string; title: string };

type LogEntry = { id: number; time: string; action: string; peer: string; ok: boolean; detail: string };

type Feedback = { tone: "ok" | "error"; title: string; detail: string; latencyMs?: number } | null;

const MESSAGE_LABELS: Record<string, string> = {
  PEER_MESSAGE: "Direct message",
  EVIDENCE_ANNOUNCEMENT: "Evidence announcement",
  INCIDENT_ANNOUNCEMENT: "Incident announcement",
};

async function apiCall<T>(path: string, method: "GET" | "POST" = "GET", body?: object): Promise<T> {
  const res = await fetch(`${BACKEND_URL}${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof data.detail === "string" ? data.detail : `Request failed (HTTP ${res.status})`;
    throw new Error(detail);
  }
  return data as T;
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className={styles.field}>
      <span className={styles.label}>{label}</span>
      {children}
    </label>
  );
}

function LinkBadge({ state }: { state: string }) {
  const connected = state === "CONNECTED";
  return (
    <span className={connected ? styles.badgeOn : styles.badgeOff}>
      ● {connected ? "CONNECTED" : "NOT CONNECTED"}
    </span>
  );
}

export default function PeersPage() {
  const [peers, setPeers] = useState<Peer[]>([]);
  const [inbox, setInbox] = useState<InboxMessage[]>([]);
  const [evidence, setEvidence] = useState<EvidenceItem[]>([]);
  const [incidents, setIncidents] = useState<IncidentItem[]>([]);
  const [selected, setSelected] = useState("");
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [log, setLog] = useState<LogEntry[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [text, setText] = useState("Direct telemetry check from peer");
  const [evidenceId, setEvidenceId] = useState("");
  const [incidentId, setIncidentId] = useState("");

  const peer = peers.find((p) => p.node_id === selected) ?? null;

  const loadPeers = useCallback(async () => {
    try {
      const data = await apiCall<Peer[]>("/api/v1/peers");
      setPeers(data);
      setSelected((current) => current || data[0]?.node_id || "");
      setLoadError(null);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Could not load peers");
    }
  }, []);

  const loadInbox = useCallback(async () => {
    try {
      const messages = await apiCall<InboxMessage[]>("/api/v1/peers/messages?page_size=50");
      // Hide heartbeat traffic so the business messages stay visible. The rows remain in the database.
      setInbox(messages.filter((m) => m.message_type !== "PING" && m.message_type !== "PONG").slice(0, 20));
    } catch {
      // Keep the last inbox state; the peer list shows the error banner.
    }
  }, []);

  const loadIncidents = useCallback(async () => {
    try {
      const inc = await apiCall<IncidentItem[]>("/api/v1/incidents");
      setIncidents(inc);
      setIncidentId((current) => current || inc[0]?.incident_id || "");
    } catch {
      // Incident announcements stay disabled until the list loads.
    }
  }, []);

  // Evidence for the chosen incident spans every node that contributed to it.
  useEffect(() => {
    if (!incidentId) return;
    const controller = new AbortController();
    apiCall<EvidenceItem[]>(`/api/v1/incidents/${incidentId}/evidence`)
      .then((ev) => {
        setEvidence(ev);
        setEvidenceId(ev[0]?.evidence_id ?? "");
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setEvidence([]);
          setEvidenceId("");
        }
      });
    return () => controller.abort();
  }, [incidentId]);

  useEffect(() => {
    // The console refreshes remote state on mount and then polls.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadPeers();
    void loadInbox();
    void loadIncidents();
    const interval = setInterval(() => {
      void loadPeers();
      void loadInbox();
    }, 4000);
    return () => clearInterval(interval);
  }, [loadPeers, loadInbox, loadIncidents]);

  const addLog = (action: string, peerId: string, ok: boolean, detail: string) => {
    setLog((prev) =>
      [
        { id: Date.now(), time: new Date().toLocaleTimeString(), action, peer: peerId, ok, detail },
        ...prev,
      ].slice(0, 8),
    );
  };

  // Every action needs an open link. Open one first if the selected node is not connected.
  const ensureConnected = async (peerId: string) => {
    const current = peers.find((p) => p.node_id === peerId);
    if (current?.connection_state === "CONNECTED") return;
    await apiCall(`/api/v1/peers/${peerId}/connect`, "POST");
  };

  const run = async (
    label: string,
    peerId: string,
    job: () => Promise<{ detail: string; latencyMs?: number }>,
  ) => {
    setBusy(true);
    setFeedback(null);
    try {
      const result = await job();
      setFeedback({ tone: "ok", title: label, detail: result.detail, latencyMs: result.latencyMs });
      addLog(label, peerId, true, result.detail);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Request failed";
      setFeedback({ tone: "error", title: `${label} failed`, detail: message });
      addLog(label, peerId, false, message);
    } finally {
      setBusy(false);
      await Promise.all([loadPeers(), loadInbox()]);
    }
  };

  const handleConnect = () =>
    run("Connect", selected, async () => {
      await apiCall(`/api/v1/peers/${selected}/connect`, "POST");
      return { detail: `Handshake complete with ${selected}. The link is open over /ws/peer.` };
    });

  const handleDisconnect = () =>
    run("Disconnect", selected, async () => {
      await apiCall(`/api/v1/peers/${selected}/disconnect`, "POST");
      return { detail: `Link to ${selected} closed.` };
    });

  const handlePing = () =>
    run("Ping", selected, async () => {
      await ensureConnected(selected);
      const res = await apiCall<{ rtt_ms: number }>(`/api/v1/peers/${selected}/ping`, "POST");
      return { detail: `${selected} answered with PONG.`, latencyMs: res.rtt_ms };
    });

  const handleSend = () =>
    run("Send message", selected, async () => {
      if (!text.trim()) throw new Error("Type a message first.");
      await ensureConnected(selected);
      const res = await apiCall<{ message_id: string }>(`/api/v1/peers/${selected}/message`, "POST", {
        text: text.trim(),
      });
      return {
        detail: `Delivered "${text.trim()}" to ${selected} directly (message ${res.message_id.slice(0, 8)}…). No broker involved.`,
      };
    });

  const handleAnnounceEvidence = () =>
    run("Announce evidence", selected, async () => {
      if (!evidenceId) throw new Error("Choose an evidence item first.");
      await ensureConnected(selected);
      await apiCall(`/api/v1/peers/${selected}/announce/evidence/${evidenceId}`, "POST");
      return { detail: `Announced ${evidenceId} to ${selected} over /ws/peer.` };
    });

  const handleAnnounceIncident = () =>
    run("Announce incident", selected, async () => {
      if (!incidentId) throw new Error("Choose an incident first.");
      await ensureConnected(selected);
      await apiCall(`/api/v1/peers/${selected}/announce/incident/${incidentId}`, "POST");
      return { detail: `Announced ${incidentId} to ${selected} over /ws/peer.` };
    });

  const connected = peer?.connection_state === "CONNECTED";

  return (
    <main className={styles.page}>
      <HeaderNav />

      <section className={styles.hero}>
        <p className={styles.kicker}>DIRECT NODE-TO-NODE MESSAGING · /ws/peer</p>
        <h1 className={styles.title}>P2P Mesh Console</h1>
        <p className={styles.subtitle}>
          Pick a node, then connect, ping, send or announce. Each action goes straight to that node over its own
          WebSocket. RabbitMQ is not in the path.
        </p>
      </section>

      <ol className={styles.steps}>
        <li><span>1</span> Select a node</li>
        <li><span>2</span> Connect (handshake)</li>
        <li><span>3</span> Ping, send or announce</li>
        <li><span>4</span> Check the inbox</li>
      </ol>

      {loadError && <div className={styles.errorBox}>{loadError}</div>}

      <div className={styles.grid}>
        <section className={styles.card}>
          <h2 className={styles.cardTitle}>1 · Select a node</h2>
          <Field label="Peer node">
            <select
              className={styles.input}
              value={selected}
              disabled={peers.length === 0}
              onChange={(e) => {
                setSelected(e.target.value);
                setFeedback(null);
              }}
            >
              {peers.map((p) => (
                <option key={p.node_id} value={p.node_id}>
                  {p.node_id} — {p.node_name}
                </option>
              ))}
            </select>
          </Field>

          {peer ? (
            <dl className={styles.facts}>
              <div><dt>Type</dt><dd>{peer.node_type}</dd></div>
              <div><dt>Address</dt><dd>{peer.p2p_host}:{peer.p2p_port}</dd></div>
              <div><dt>Link</dt><dd><LinkBadge state={peer.connection_state} /></dd></div>
              <div><dt>Last round trip</dt><dd>{peer.rtt_ms != null ? `${peer.rtt_ms} ms` : "—"}</dd></div>
            </dl>
          ) : (
            <p className={styles.muted}>No peers registered. Use Re-Seed on the System page.</p>
          )}

          <div className={styles.buttonRow}>
            <button className={styles.primary} disabled={!peer || busy || connected} onClick={handleConnect}>
              Connect
            </button>
            <button className={styles.secondary} disabled={!peer || busy || !connected} onClick={handleDisconnect}>
              Disconnect
            </button>
          </div>
        </section>

        <section className={styles.card}>
          <h2 className={styles.cardTitle}>2 · Choose an action</h2>
          <p className={styles.muted}>Actions open the link automatically if it is closed.</p>

          <div className={styles.action}>
            <div className={styles.actionText}>
              <strong>Ping</strong>
              <span>Measure the round-trip time</span>
            </div>
            <button className={styles.primary} disabled={!peer || busy} onClick={handlePing}>Ping</button>
          </div>

          <div className={styles.action}>
            <div className={styles.actionText}>
              <strong>Send message</strong>
              <input className={styles.input} value={text} onChange={(e) => setText(e.target.value)} />
            </div>
            <button className={styles.primary} disabled={!peer || busy} onClick={handleSend}>Send</button>
          </div>

          <div className={styles.action}>
            <div className={styles.actionText}>
              <strong>Announce evidence</strong>
              <select className={styles.input} value={evidenceId} onChange={(e) => setEvidenceId(e.target.value)}>
                {evidence.length === 0 && <option value="">No evidence in this incident</option>}
                {evidence.map((ev) => (
                  <option key={ev.evidence_id} value={ev.evidence_id}>
                    {ev.evidence_id} · {ev.node_id} — {ev.title}
                  </option>
                ))}
              </select>
            </div>
            <button className={styles.secondary} disabled={!peer || busy || !evidenceId} onClick={handleAnnounceEvidence}>
              Announce
            </button>
          </div>

          <div className={styles.action}>
            <div className={styles.actionText}>
              <strong>Announce incident</strong>
              <select className={styles.input} value={incidentId} onChange={(e) => setIncidentId(e.target.value)}>
                {incidents.length === 0 && <option value="">No incidents loaded</option>}
                {incidents.map((inc) => (
                  <option key={inc.incident_id} value={inc.incident_id}>
                    {inc.incident_id} — {inc.title}
                  </option>
                ))}
              </select>
            </div>
            <button className={styles.secondary} disabled={!peer || busy || !incidentId} onClick={handleAnnounceIncident}>
              Announce
            </button>
          </div>
        </section>
      </div>

      <section className={styles.resultCard}>
        <h2 className={styles.cardTitle}>Result</h2>
        {feedback ? (
          <div className={feedback.tone === "ok" ? styles.resultOk : styles.resultError}>
            <strong>{feedback.tone === "ok" ? "✓" : "✗"} {feedback.title}</strong>
            <p>{feedback.detail}</p>
            {feedback.latencyMs != null && <span className={styles.latency}>{feedback.latencyMs} ms</span>}
          </div>
        ) : (
          <p className={styles.muted}>Run an action to see the result here.</p>
        )}
      </section>

      <div className={styles.grid}>
        <section className={styles.card}>
          <h2 className={styles.cardTitle}>Session log</h2>
          {log.length === 0 ? (
            <p className={styles.muted}>Actions you run appear here, newest first.</p>
          ) : (
            <ul className={styles.logList}>
              {log.map((entry) => (
                <li key={entry.id}>
                  <span className={styles.logTime}>{entry.time}</span>
                  <span className={entry.ok ? styles.badgeOn : styles.badgeError}>{entry.ok ? "OK" : "FAILED"}</span>
                  <span>
                    <strong>{entry.action}</strong> → {entry.peer}
                    <small className={styles.logDetail}>{entry.detail}</small>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className={styles.card}>
          <div className={styles.cardHeader}>
            <h2 className={styles.cardTitle}>Inbox — messages received</h2>
            <button className={styles.secondary} onClick={() => void loadInbox()}>Refresh</button>
          </div>
          {inbox.length === 0 ? (
            <p className={styles.muted}>No messages yet. Send one or announce an item, then refresh.</p>
          ) : (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>From</th>
                    <th>Type</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {inbox.map((msg) => (
                    <tr key={msg.id}>
                      <td>{new Date(msg.received_at).toLocaleTimeString()}</td>
                      <td><strong>{msg.source_node_id}</strong></td>
                      <td>{MESSAGE_LABELS[msg.message_type] ?? msg.message_type}</td>
                      <td>
                        <span className={msg.status === "PROCESSED" ? styles.badgeOn : styles.badgeOff}>
                          {msg.status}
                        </span>
                        {msg.error_message && <small className={styles.logDetail}>{msg.error_message}</small>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
