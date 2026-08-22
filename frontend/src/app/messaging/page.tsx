"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import styles from "./page.module.css";

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

export default function MessagingPage() {
  const [records, setRecords] = useState<MessageRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mqHealth, setMqHealth] = useState<MQHealth | null>(null);

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
      setTestResult("✓ Published successfully");
      setTimeout(() => void load(), 800);
    } catch (err) {
      setTestResult(`✗ ${err instanceof Error ? err.message : "Error"}`);
    } finally {
      setTestBusy(false);
    }
  }

  return (
    <main className={styles.page}>
      {/* ── Header ── */}
      <header className={styles.header}>
        <Link href="/" className={styles.logo}>EV</Link>
        <span>MESSAGE-ORIENTED COMMUNICATION / 06</span>
        <nav className={styles.nav}>
          <Link href="/nodes">Nodes</Link>
          <Link href="/evidence">Evidence</Link>
          <Link href="/incidents">Incidents</Link>
        </nav>
      </header>

      {/* ── Hero ── */}
      <section className={styles.hero}>
        <p className={styles.kicker}>RABBITMQ ASYNC MESSAGING</p>
        <h1>Messaging Monitor</h1>
        <p className={styles.sub}>
          Local inbox for asynchronous events received from the
          distributed node network via the <code>echovault.events</code> exchange.
        </p>
        <div className={styles.healthRow}>
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
          <button className={styles.refreshBtn} onClick={() => void load()}>
            ↺ Refresh
          </button>
        </div>
      </section>

      {/* ── Architecture note ── */}
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

      {/* ── Message Table ── */}
      <section className={styles.tableSection}>
        <div className={styles.tableHeader}>
          <h2>Received Messages</h2>
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
          <p>Publish a test event through RabbitMQ to demonstrate message routing.</p>
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
