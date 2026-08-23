"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
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
};
type Node = {
  node_id: string;
  node_name: string;
  role: string;
  status: string;
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

function relative(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const secs = Math.floor(diff / 1000);
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  return new Date(iso).toLocaleTimeString();
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
      setNodes(await responses[2].json());
      setLocalEvidence(await responses[3].json());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to load incident.");
    }
  }, []);

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
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastEventId]);

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

  if (error && !incident)
    return (
      <main className={styles.page}>
        <p className={styles.error}>{error}</p>
      </main>
    );
  if (!incident)
    return (
      <main className={styles.page}>
        <p className={styles.message}>Loading incident…</p>
      </main>
    );

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <Link href="/" className={styles.logo}>
          EV
        </Link>
        <span>INCIDENT / {incident.incident_id}</span>
        <WsStatusDot status={wsStatus} />
        <Link href="/incidents">All incidents</Link>
      </header>

      <section className={styles.hero}>
        <p className={styles.kicker}>
          {incident.incident_type} · {incident.severity}
        </p>
        <h1>{incident.title}</h1>
        <p>{incident.description || "No description provided."}</p>
      </section>

      {error && <p className={styles.error}>{error}</p>}

      <section className={styles.content}>
        <div className={styles.panel}>
          <div className={styles.heading}>
            <h2>Incident information</h2>
            <span>{incident.incident_id}</span>
          </div>
          <dl className={styles.details}>
            <div>
              <dt>Status</dt>
              <dd>{incident.status}</dd>
            </div>
            <div>
              <dt>Created by</dt>
              <dd>{incident.created_by_node_id}</dd>
            </div>
            <div>
              <dt>Started</dt>
              <dd>{new Date(incident.started_at).toLocaleString()}</dd>
            </div>
            <div>
              <dt>Location</dt>
              <dd>
                {incident.location ? JSON.stringify(incident.location) : "—"}
              </dd>
            </div>
          </dl>
          <div className={styles.actions}>
            {incident.status === "OPEN" && (
              <button onClick={() => void statusChange("INVESTIGATING")}>
                Start investigation
              </button>
            )}
            {incident.status === "INVESTIGATING" && (
              <button onClick={() => void statusChange("RESOLVED")}>
                Mark resolved
              </button>
            )}
            {incident.status === "RESOLVED" && (
              <button onClick={() => void statusChange("CLOSED")}>
                Close incident
              </button>
            )}
          </div>
        </div>

        {/* ── Live Activity Feed ── */}
        <div className={`${styles.panel} ${styles.activityPanel}`}>
          <div className={styles.heading}>
            <h2>Live Incident Activity</h2>
            <WsStatusDot status={wsStatus} />
          </div>
          <div className={styles.activityFeed}>
            {wsStatus === "connecting" && (
              <p className={styles.message}>Connecting to event stream…</p>
            )}
            {wsStatus === "connected" && liveEvents.length === 0 && (
              <p className={styles.message}>
                Subscribed to <code>{id}</code>.<br />
                <small>Events will appear here automatically.</small>
              </p>
            )}
            {liveEvents.map((ev) => (
              <ActivityItem key={ev.message_id} event={ev} />
            ))}
          </div>
        </div>

        <div className={styles.panel}>
          <div className={styles.heading}>
            <h2>Participating nodes</h2>
            <span>{nodes.length.toString().padStart(2, "0")}</span>
          </div>
          {nodes.length ? (
            <ul className={styles.items}>
              {nodes.map((node) => (
                <li key={node.node_id}>
                  <strong>{node.node_id}</strong>
                  <span>
                    {node.node_name} · {node.role} · {node.status}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className={styles.message}>No participating nodes recorded.</p>
          )}
        </div>
      </section>

      <section className={styles.panel + " " + styles.listPanel}>
        <div className={styles.heading}>
          <h2>Local evidence</h2>
          <span>{evidence.length.toString().padStart(2, "0")} ATTACHED</span>
        </div>
        {evidence.length ? (
          <div className={styles.table}>
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Event</th>
                  <th>Type</th>
                  <th>Title</th>
                  <th>Captured</th>
                </tr>
              </thead>
              <tbody>
                {evidence.map((item) => (
                  <tr key={item.evidence_id}>
                    <td>{item.evidence_id}</td>
                    <td>{item.event_type}</td>
                    <td>{item.evidence_type}</td>
                    <td>{item.title}</td>
                    <td>{new Date(item.captured_at).toLocaleString()}</td>
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
          <div className={styles.attach}>
            <h3>Attach local evidence</h3>
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
                  {item.evidence_id} · {item.title}
                </button>
              ))}
          </div>
        )}
      </section>
    </main>
  );
}
