"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { useEventStream, type WsEvent } from "../../hooks/useEventStream";
import styles from "./page.module.css";

// ── Types ────────────────────────────────────────────────────────────────────

type MessageRecord = {
  id: string;
  message_id: string;
  source_node_id: string;
  event_type: string;
  routing_key: string;
  incident_id: string | null;
  received_at: string;
  processed_at: string | null;
  status: "RECEIVED" | "PROCESSED" | "FAILED" | "IGNORED";
  error_message: string | null;
};

type MQHealth = {
  service: string;
  status: "healthy" | "unhealthy";
};

type WsHealth = {
  service: string;
  status: string;
  active_connections: number;
};

// ── Constants ─────────────────────────────────────────────────────────────────

const backendUrl =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

const EVENT_TYPES = [
  "evidence.created",
  "evidence.updated",
  "evidence.deleted",
  "incident.created",
  "incident.updated",
  "incident.closed",
  "incident.evidence_associated",
  "incident.evidence_removed",
  "node.registered",
  "node.status_changed",
  "test.message",
];

const STATUS_OPTIONS = ["RECEIVED", "PROCESSED", "FAILED", "IGNORED"];

const SUBSCRIPTION_PRESETS = [
  { label: "All Events", filters: {} },
  { label: "Evidence Only", filters: { event_types: ["evidence.created", "evidence.updated", "evidence.deleted"] } },
  { label: "Incident Only", filters: { event_types: ["incident.created", "incident.updated", "incident.closed", "incident.evidence_associated", "incident.evidence_removed"] } },
  { label: "Node Only", filters: { event_types: ["node.registered", "node.status_changed"] } },
];

const MAX_LIVE_EVENTS = 100;

// ── Helper components ─────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: MessageRecord["status"] }) {
  return <span className={`${styles.badge} ${styles[`badge_${status}`]}`}>{status}</span>;
}

function EventChip({ type }: { type: string }) {
  const category = type.split(".")[0];
  return <span className={`${styles.chip} ${styles[`chip_${category}`]}`}>{type}</span>;
}

function relative(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const secs = Math.floor(diff / 1000);
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  return new Date(iso).toLocaleTimeString();
}

function WsStatusPill({ status }: { status: string }) {
  const dotClass =
    status === "connected"
      ? styles.dotHealthy
      : status === "connecting"
      ? styles.dotConnecting
      : styles.dotUnhealthy;
  const label =
    status === "connected"
      ? "LIVE"
      : status === "connecting"
      ? "CONNECTING"
      : status === "error"
      ? "ERROR"
      : "DISCONNECTED";

  return (
    <span className={styles.wsStatusPill}>
      <span className={`${styles.healthDot} ${dotClass}`} />
      <span className={styles.wsStatusLabel}>{label}</span>
    </span>
  );
}

function LiveEventItem({ event }: { event: WsEvent }) {
  const time = new Date(event.timestamp).toLocaleTimeString();
  const category = event.event_type.split(".")[0];
  return (
    <div className={`${styles.liveItem} ${styles.liveItemNew}`}>
      <div className={styles.liveItemTime}>{time}</div>
      <div className={styles.liveItemBody}>
        <span className={`${styles.chip} ${styles[`chip_${category}`]}`}>
          {event.event_type}
        </span>
        <span className={styles.liveItemSource}>{event.source_node_id}</span>
        {event.incident_id && (
          <span className={styles.liveItemIncident}>{event.incident_id}</span>
        )}
        {event.latency_ms !== null && (
          <span className={styles.liveItemLatency}>{event.latency_ms}ms</span>
        )}
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function MessagingPage() {
  // ── REST state ────────────────────────────────────────────────────────────
  const [records, setRecords] = useState<MessageRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mqHealth, setMqHealth] = useState<MQHealth | null>(null);
  const [wsHealth, setWsHealth] = useState<WsHealth | null>(null);

  const [filterEvent, setFilterEvent] = useState("");
  const [filterSource, setFilterSource] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [filterIncident, setFilterIncident] = useState("");

  const [testEvent, setTestEvent] = useState("test.message");
  const [testMsg, setTestMsg] = useState("Hello from this node");
  const [testBusy, setTestBusy] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);

  const [page, setPage] = useState(1);
  const PAGE_SIZE = 50;

  // ── WebSocket state ───────────────────────────────────────────────────────
  const [activePreset, setActivePreset] = useState(0); // index into SUBSCRIPTION_PRESETS
  const [customIncidentId, setCustomIncidentId] = useState("");
  const [customNodeId, setCustomNodeId] = useState("");
  const feedRef = useRef<HTMLDivElement>(null);

  // useEventStream — starts with all events (no filter)
  const { status: wsStatus, connectionId, events: liveEvents, subscribe, unsubscribe, clearEvents } =
    useEventStream({
      filters: SUBSCRIPTION_PRESETS[0].filters,
    });

  // Scroll live feed to top on new events
  useEffect(() => {
    if (feedRef.current) {
      feedRef.current.scrollTop = 0;
    }
  }, [liveEvents.length]);

  // Apply preset subscription when changed
  useEffect(() => {
    const preset = SUBSCRIPTION_PRESETS[activePreset];
    // Unsubscribe everything first, then subscribe to preset
    unsubscribe({
      event_types: EVENT_TYPES,
      source_node_ids: [],
      incident_ids: [],
    });
    if (Object.keys(preset.filters).length > 0) {
      subscribe(preset.filters);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activePreset]);

  // Fetch WS health periodically
  useEffect(() => {
    async function fetchWsHealth() {
      try {
        const res = await fetch(`${backendUrl}/health/websocket`);
        if (res.ok) setWsHealth(await res.json());
      } catch {/* ignore */}
    }
    void fetchWsHealth();
    const id = setInterval(() => void fetchWsHealth(), 10_000);
    return () => clearInterval(id);
  }, []);

  // ── REST load ─────────────────────────────────────────────────────────────
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filterEvent) params.set("event_type", filterEvent);
      if (filterSource) params.set("source_node_id", filterSource);
      if (filterStatus) params.set("status", filterStatus);
      if (filterIncident) params.set("incident_id", filterIncident);
      params.set("page", String(page));
      params.set("page_size", String(PAGE_SIZE));

      const [msgRes, healthRes] = await Promise.all([
        fetch(`${backendUrl}/api/v1/messaging/messages?${params}`),
        fetch(`${backendUrl}/health/messaging`).catch(() => null),
      ]);

      if (!msgRes.ok) throw new Error("Failed to load message history");
      setRecords(await msgRes.json());
      setError(null);

      if (healthRes) {
        if (healthRes.ok) {
          setMqHealth({ service: "rabbitmq", status: "healthy" });
        } else {
          const detail = await healthRes.json().catch(() => null);
          setMqHealth(detail?.detail ?? { service: "rabbitmq", status: "unhealthy" });
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [filterEvent, filterSource, filterStatus, filterIncident, page]);

  useEffect(() => {
    void load();
  }, [load]);

  // After a live event arrives, refresh history after a short delay
  const lastEventId = liveEvents[0]?.message_id;
  const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (!lastEventId) return;
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    refreshTimerRef.current = setTimeout(() => void load(), 1500);
    return () => {
      if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastEventId]);

  // ── Test publisher ────────────────────────────────────────────────────────
  async function publishTest() {
    setTestBusy(true);
    setTestResult(null);
    try {
      const res = await fetch(`${backendUrl}/api/v1/messaging/test`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          event_type: testEvent,
          payload: { message: testMsg },
        }),
      });
      const body = await res.json().catch(() => null);
      if (!res.ok) throw new Error(body?.detail ?? "Publish failed");
      setTestResult("✓ Published — watch the live feed above");
    } catch (err) {
      setTestResult(`✗ ${err instanceof Error ? err.message : "Error"}`);
    } finally {
      setTestBusy(false);
    }
  }

  // ── Subscription helpers ──────────────────────────────────────────────────
  function applyCustomIncident() {
    const id = customIncidentId.trim();
    if (!id) return;
    subscribe({ incident_ids: [id] });
  }
  function applyCustomNode() {
    const id = customNodeId.trim();
    if (!id) return;
    subscribe({ source_node_ids: [id] });
  }

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <main className={styles.page}>
      {/* ── Header ── */}
      <header className={styles.header}>
        <Link href="/" className={styles.logo}>EV</Link>
        <span>STREAM-ORIENTED COMMUNICATION / 07</span>
        <nav className={styles.nav}>
          <Link href="/nodes">Nodes</Link>
          <Link href="/evidence">Evidence</Link>
          <Link href="/incidents">Incidents</Link>
          <Link href="/peers">Peers</Link>
        </nav>
      </header>

      {/* ── Hero ── */}
      <section className={styles.hero}>
        <p className={styles.kicker}>RABBITMQ + WEBSOCKET EVENT STREAM</p>
        <h1>Messaging Monitor</h1>
        <p className={styles.sub}>
          Real-time distributed events via <code>WebSocket</code> stream, backed by
          the <code>echovault.events</code> RabbitMQ exchange for persistence.
        </p>

        {/* Status row */}
        <div className={styles.statusRow}>
          <div className={styles.statusItem}>
            <span className={styles.healthLabel}>RabbitMQ</span>
            <span
              className={`${styles.healthDot} ${
                mqHealth?.status === "healthy"
                  ? styles.dotHealthy
                  : mqHealth?.status === "unhealthy"
                  ? styles.dotUnhealthy
                  : styles.dotUnknown
              }`}
            />
            <span className={styles.healthStatus}>
              {mqHealth?.status ?? "checking…"}
            </span>
          </div>
          <div className={styles.statusDivider} />
          <div className={styles.statusItem}>
            <span className={styles.healthLabel}>WebSocket</span>
            <WsStatusPill status={wsStatus} />
          </div>
          {connectionId && (
            <>
              <div className={styles.statusDivider} />
              <div className={styles.statusItem}>
                <span className={styles.healthLabel}>Active Clients</span>
                <span className={styles.healthStatus}>
                  {wsHealth?.active_connections ?? "…"}
                </span>
              </div>
            </>
          )}
          <button className={styles.refreshBtn} onClick={() => void load()}>
            ↺ Refresh history
          </button>
        </div>
      </section>

      {/* ── Architecture banner ── */}
      <section className={styles.archBanner}>
        <div className={styles.archItem}>
          <span className={styles.archIcon}>⚡</span>
          <div>
            <strong>gRPC (Part 5)</strong>
            <p>Synchronous — Node A needs an immediate response from Node B</p>
          </div>
        </div>
        <div className={styles.archDivider}>vs</div>
        <div className={styles.archItem}>
          <span className={styles.archIcon}>📨</span>
          <div>
            <strong>RabbitMQ (Part 6)</strong>
            <p>Asynchronous — Node A announces an event to N subscribers</p>
          </div>
        </div>
        <div className={styles.archDivider}>vs</div>
        <div className={styles.archItem}>
          <span className={styles.archIcon}>⚡🌊</span>
          <div>
            <strong>WebSocket (Part 7)</strong>
            <p>Stream — backend pushes events to browser clients continuously</p>
          </div>
        </div>
      </section>

      {/* ── WebSocket live panel ── */}
      <section className={styles.liveSection}>
        {/* Subscription controls */}
        <div className={styles.liveControls}>
          <div className={styles.liveControlsLeft}>
            <span className={styles.liveSectionTitle}>
              <span className={styles.livePulse} />
              LIVE ACTIVITY
            </span>
            <div className={styles.presetRow}>
              {SUBSCRIPTION_PRESETS.map((p, i) => (
                <button
                  key={p.label}
                  className={`${styles.presetBtn} ${activePreset === i ? styles.presetBtnActive : ""}`}
                  onClick={() => setActivePreset(i)}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>
          <div className={styles.liveControlsRight}>
            <div className={styles.customFilter}>
              <input
                className={styles.customFilterInput}
                placeholder="Subscribe to incident (e.g. INC-000001)"
                value={customIncidentId}
                onChange={(e) => setCustomIncidentId(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && applyCustomIncident()}
                id="ws-subscribe-incident"
              />
              <button className={styles.customFilterBtn} onClick={applyCustomIncident}>
                + Subscribe
              </button>
            </div>
            <div className={styles.customFilter}>
              <input
                className={styles.customFilterInput}
                placeholder="Subscribe to node (e.g. CCTV-A)"
                value={customNodeId}
                onChange={(e) => setCustomNodeId(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && applyCustomNode()}
                id="ws-subscribe-node"
              />
              <button className={styles.customFilterBtn} onClick={applyCustomNode}>
                + Subscribe
              </button>
            </div>
            <button className={styles.clearBtn} onClick={clearEvents}>
              Clear feed
            </button>
          </div>
        </div>

        {/* Live feed */}
        <div className={styles.liveFeed} ref={feedRef}>
          {wsStatus === "connecting" && (
            <div className={styles.liveState}>
              <span className={styles.spinner} />
              Connecting to WebSocket event stream…
            </div>
          )}
          {wsStatus === "disconnected" && (
            <div className={styles.liveState}>
              WebSocket disconnected — reconnecting with backoff…
            </div>
          )}
          {wsStatus === "connected" && liveEvents.length === 0 && (
            <div className={styles.liveState}>
              <span className={styles.livePulse} />
              Connected. Waiting for events…
              <small>Events from all nodes will appear here in real time.</small>
            </div>
          )}
          {liveEvents.slice(0, MAX_LIVE_EVENTS).map((ev) => (
            <LiveEventItem key={ev.message_id} event={ev} />
          ))}
        </div>

        {liveEvents.length > 0 && (
          <div className={styles.liveFeedFooter}>
            Showing {Math.min(liveEvents.length, MAX_LIVE_EVENTS)} of{" "}
            {liveEvents.length} events · WebSocket connection_id:{" "}
            <code>{connectionId ?? "—"}</code>
          </div>
        )}
      </section>

      {/* ── Filters ── */}
      <section className={styles.filters}>
        <select
          value={filterEvent}
          onChange={(e) => { setPage(1); setFilterEvent(e.target.value); }}
          id="filter-event-type"
        >
          <option value="">All event types</option>
          {EVENT_TYPES.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <select
          value={filterStatus}
          onChange={(e) => { setPage(1); setFilterStatus(e.target.value); }}
          id="filter-status"
        >
          <option value="">All statuses</option>
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <input
          placeholder="Source node (e.g. CCTV-A)"
          value={filterSource}
          onChange={(e) => { setPage(1); setFilterSource(e.target.value); }}
          id="filter-source-node"
        />
        <input
          placeholder="Incident ID"
          value={filterIncident}
          onChange={(e) => { setPage(1); setFilterIncident(e.target.value); }}
          id="filter-incident-id"
        />
      </section>

      {/* ── Message History Table ── */}
      <section className={styles.tableSection}>
        <div className={styles.tableHeader}>
          <h2>Received Message History</h2>
          <span className={styles.count}>{records.length} records</span>
        </div>

        {loading ? (
          <div className={styles.state}>
            <span className={styles.spinner} />
            Loading messages…
          </div>
        ) : error ? (
          <div className={styles.stateError}>{error}</div>
        ) : records.length === 0 ? (
          <div className={styles.state}>
            No messages match the current filters.
            <br />
            <small>Messages appear here once this node receives them via RabbitMQ.</small>
          </div>
        ) : (
          <div className={styles.tableWrap}>
            <table>
              <thead>
                <tr>
                  <th>Message ID</th>
                  <th>Event</th>
                  <th>Source Node</th>
                  <th>Incident</th>
                  <th>Received</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {records.map((r) => (
                  <tr key={r.id} className={r.status === "FAILED" ? styles.rowFailed : ""}>
                    <td className={styles.monoCell}>
                      <span title={r.message_id}>{r.message_id.slice(0, 12)}…</span>
                    </td>
                    <td><EventChip type={r.event_type} /></td>
                    <td className={styles.nodeCell}>{r.source_node_id}</td>
                    <td className={styles.monoCell}>{r.incident_id ?? "—"}</td>
                    <td title={r.received_at}>{relative(r.received_at)}</td>
                    <td><StatusBadge status={r.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        <div className={styles.pagination}>
          <button
            className={styles.pageBtn}
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
          >
            ← Prev
          </button>
          <span>Page {page}</span>
          <button
            className={styles.pageBtn}
            disabled={records.length < PAGE_SIZE}
            onClick={() => setPage((p) => p + 1)}
          >
            Next →
          </button>
        </div>
      </section>

      {/* ── Dev Test Publisher ── */}
      <section className={styles.devPanel}>
        <div className={styles.devHeader}>
          <span className={styles.devBadge}>DEV ONLY</span>
          <h2>Test Publisher</h2>
          <p>
            Publish a test event through RabbitMQ. It will immediately appear in
            the live feed above via WebSocket — no page refresh needed.
          </p>
        </div>
        <div className={styles.devForm}>
          <label>
            Event type
            <select
              value={testEvent}
              onChange={(e) => setTestEvent(e.target.value)}
              id="test-event-type"
            >
              {EVENT_TYPES.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </label>
          <label className={styles.wide}>
            Message
            <input
              value={testMsg}
              onChange={(e) => setTestMsg(e.target.value)}
              placeholder="Hello from this node"
              id="test-message"
            />
          </label>
          <button
            className={styles.publishBtn}
            disabled={testBusy}
            onClick={() => void publishTest()}
          >
            {testBusy ? "Publishing…" : "Publish test event →"}
          </button>
        </div>
        {testResult && (
          <p
            className={
              testResult.startsWith("✓") ? styles.testSuccess : styles.testError
            }
          >
            {testResult}
          </p>
        )}
      </section>
    </main>
  );
}
