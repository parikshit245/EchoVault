"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import styles from "./page.module.css";

type Incident = {
  id: string;
  incident_id: string;
  title: string;
  incident_type: string;
  description: string | null;
  status: string;
  severity: string;
  location: Record<string, unknown> | null;
  started_at: string;
  created_at: string;
  created_by_node_id: string;
};
const api = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
const types = [
  "SECURITY",
  "ACCIDENT",
  "INTRUSION",
  "THEFT",
  "VANDALISM",
  "INFRASTRUCTURE",
  "OTHER",
];
const severities = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];

export default function IncidentsPage() {
  const [items, setItems] = useState<Incident[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    try {
      const r = await fetch(`${api}/api/v1/incidents`);
      if (!r.ok) throw new Error("Unable to load incidents.");
      setItems(await r.json());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to load incidents.");
    }
  }, []);
  useEffect(() => {
    // Synchronize with the external incident registry API.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    const form = new FormData(event.currentTarget);
    try {
      const r = await fetch(`${api}/api/v1/incidents`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: form.get("title"),
          incident_type: form.get("incident_type"),
          description: form.get("description") || null,
          severity: form.get("severity"),
          started_at: new Date(
            String(form.get("started_at") || new Date().toISOString()),
          ).toISOString(),
          location: form.get("location")
            ? JSON.parse(String(form.get("location")))
            : null,
        }),
      });
      if (!r.ok) {
        const d = await r.json().catch(() => null);
        throw new Error(d?.detail || "Incident creation failed.");
      }
      event.currentTarget.reset();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Incident creation failed.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <Link href="/" className={styles.logo}>
          EV
        </Link>
        <span>INCIDENT SERVICE / 04</span>
        <Link href="/nodes">Node registry</Link>
      </header>
      <section className={styles.hero}>
        <p className={styles.kicker}>SHARED LOGICAL CONTEXT</p>
        <h1>Incidents</h1>
        <p>
          Connect local observations without transferring evidence ownership.
        </p>
      </section>
      <section className={styles.content}>
        <div className={styles.panel}>
          <div className={styles.heading}>
            <h2>Create incident</h2>
            <span>CREATOR IS SERVER NODE</span>
          </div>
          <form className={styles.form} onSubmit={(e) => void create(e)}>
            <label>
              Title
              <input
                name="title"
                placeholder="Restricted Area Intrusion"
                required
              />
            </label>
            <label>
              Type
              <select name="incident_type" defaultValue="SECURITY">
                {types.map((x) => (
                  <option key={x}>{x}</option>
                ))}
              </select>
            </label>
            <label>
              Severity
              <select name="severity" defaultValue="MEDIUM">
                {severities.map((x) => (
                  <option key={x}>{x}</option>
                ))}
              </select>
            </label>
            <label>
              Started at
              <input name="started_at" type="datetime-local" />
            </label>
            <label className={styles.wide}>
              Description
              <textarea name="description" rows={2} />
            </label>
            <label className={styles.wide}>
              Location JSON
              <textarea
                name="location"
                rows={2}
                placeholder={'{"zone":"Entrance"}'}
              />
            </label>
            <button disabled={busy}>
              {busy ? "Creating…" : "Create incident"}
            </button>
          </form>
        </div>
        <div className={styles.panel}>
          <div className={styles.heading}>
            <h2>Incident register</h2>
            <span>{items.length.toString().padStart(2, "0")} INCIDENTS</span>
          </div>
          {error ? (
            <p className={styles.error}>{error}</p>
          ) : items.length === 0 ? (
            <p className={styles.message}>No incidents recorded.</p>
          ) : (
            <div className={styles.table}>
              <table>
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Title</th>
                    <th>Type</th>
                    <th>Severity</th>
                    <th>Status</th>
                    <th>Created by</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((x) => (
                    <tr key={x.id}>
                      <td>
                        <Link href={`/incidents/${x.incident_id}`}>
                          {x.incident_id}
                        </Link>
                      </td>
                      <td>{x.title}</td>
                      <td>{x.incident_type}</td>
                      <td>{x.severity}</td>
                      <td>
                        <span className={styles[x.status.toLowerCase()]}>
                          {x.status}
                        </span>
                      </td>
                      <td>{x.created_by_node_id}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>
    </main>
  );
}
