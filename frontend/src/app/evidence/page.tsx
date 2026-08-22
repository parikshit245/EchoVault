"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import styles from "./page.module.css";

type Evidence = {
  id: string;
  evidence_id: string;
  node_id: string;
  node_name: string;
  evidence_type: string;
  event_type: string;
  title: string;
  captured_at: string;
  file_name: string | null;
  file_size: number | null;
};

const backendUrl =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
const evidenceTypes = ["IMAGE", "VIDEO", "AUDIO", "TEXT", "SENSOR", "OTHER"];
const eventTypes = [
  "MOTION_DETECTED",
  "PERSON_DETECTED",
  "AUDIO_DETECTED",
  "DOOR_OPENED",
  "OBJECT_DETECTED",
  "MANUAL_OBSERVATION",
  "OTHER",
];

function isoDate(value: FormDataEntryValue | null): string | undefined {
  if (typeof value !== "string" || !value) return undefined;
  return value.endsWith("Z") ? value : `${value}:00Z`;
}

export default function EvidencePage() {
  const [records, setRecords] = useState<Evidence[]>([]);
  const [nodeId, setNodeId] = useState("current node");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [evidenceResponse, selfResponse] = await Promise.all([
        fetch(`${backendUrl}/api/v1/evidence`),
        fetch(`${backendUrl}/api/v1/node/self`),
      ]);
      if (!evidenceResponse.ok)
        throw new Error("Unable to load local evidence.");
      setRecords(await evidenceResponse.json());
      if (selfResponse.ok) setNodeId((await selfResponse.json()).node_id);
      setError(null);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to load local evidence.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Synchronize this client page with the external evidence registry API.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  async function submit(event: FormEvent<HTMLFormElement>, upload: boolean) {
    event.preventDefault();
    setBusy(true);
    const form = new FormData(event.currentTarget);
    try {
      let response: Response;
      if (upload) {
        const file = form.get("file");
        if (!(file instanceof File) || !file.name)
          throw new Error("Select a file first.");
        form.set(
          "captured_at",
          isoDate(form.get("captured_at")) ?? new Date().toISOString(),
        );
        response = await fetch(`${backendUrl}/api/v1/evidence/upload`, {
          method: "POST",
          body: form,
        });
      } else {
        const location = form.get("location");
        const metadata = form.get("metadata");
        const payload = {
          evidence_type: form.get("evidence_type"),
          event_type: form.get("event_type"),
          title: form.get("title"),
          description: form.get("description") || null,
          captured_at: isoDate(form.get("captured_at")),
          incident_id: form.get("incident_id") || null,
          location: location ? JSON.parse(String(location)) : null,
          metadata: metadata ? JSON.parse(String(metadata)) : null,
        };
        response = await fetch(`${backendUrl}/api/v1/evidence`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
      }
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        throw new Error(
          typeof detail?.detail === "string"
            ? detail.detail
            : "Evidence creation failed.",
        );
      }
      event.currentTarget.reset();
      await load();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Evidence creation failed.",
      );
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
        <span>EVIDENCE NODE / 03</span>
        <Link href="/nodes">Node registry</Link>
      </header>
      <section className={styles.hero}>
        <p className={styles.kicker}>LOCAL OWNERSHIP LAYER</p>
        <h1>Evidence</h1>
        <p>
          Observations created here belong only to <strong>{nodeId}</strong>.
        </p>
      </section>
      <section className={styles.content}>
        <div className={styles.panel}>
          <div className={styles.panelHeading}>
            <h2>Create observation</h2>
            <span>METADATA</span>
          </div>
          <form
            className={styles.form}
            onSubmit={(event) => void submit(event, false)}
          >
            <label>
              Event type
              <select name="event_type" defaultValue="MANUAL_OBSERVATION">
                {eventTypes.map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </select>
            </label>
            <label>
              Evidence type
              <select name="evidence_type" defaultValue="IMAGE">
                {evidenceTypes.map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </select>
            </label>
            <label className={styles.wide}>
              Title
              <input
                name="title"
                placeholder="Motion detected at entrance"
                required
              />
            </label>
            <label className={styles.wide}>
              Description
              <textarea
                name="description"
                rows={2}
                placeholder="Optional observation details"
              />
            </label>
            <label>
              Captured at
              <input name="captured_at" type="datetime-local" />
            </label>
            <label>
              Incident ID
              <input name="incident_id" placeholder="Optional, for Part 4" />
            </label>
            <label className={styles.wide}>
              Location JSON
              <textarea
                name="location"
                rows={2}
                placeholder={'{"zone":"Entrance"}'}
              />
            </label>
            <label className={styles.wide}>
              Metadata JSON
              <textarea
                name="metadata"
                rows={2}
                placeholder={'{"confidence":0.94}'}
              />
            </label>
            <button disabled={busy}>Create evidence</button>
          </form>
        </div>
        <div className={styles.panel}>
          <div className={styles.panelHeading}>
            <h2>Upload file</h2>
            <span>MAX 50 MB</span>
          </div>
          <form
            className={styles.form}
            onSubmit={(event) => void submit(event, true)}
            encType="multipart/form-data"
          >
            <label>
              Event type
              <select name="event_type" defaultValue="MANUAL_OBSERVATION">
                {eventTypes.map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </select>
            </label>
            <label>
              Evidence type
              <select name="evidence_type" defaultValue="IMAGE">
                {evidenceTypes.map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </select>
            </label>
            <label className={styles.wide}>
              Title
              <input name="title" placeholder="Uploaded observation" required />
            </label>
            <label className={styles.wide}>
              File
              <input
                name="file"
                type="file"
                accept="image/jpeg,image/png,video/mp4,video/webm,audio/mpeg,audio/wav,audio/webm,text/plain,application/pdf"
                required
              />
            </label>
            <label className={styles.wide}>
              Description
              <textarea
                name="description"
                rows={2}
                placeholder="Optional upload details"
              />
            </label>
            <label className={styles.wide}>
              Captured at
              <input name="captured_at" type="datetime-local" />
            </label>
            <button disabled={busy}>Upload evidence</button>
          </form>
        </div>
      </section>
      <section className={styles.panel + " " + styles.listPanel}>
        <div className={styles.panelHeading}>
          <h2>Local evidence</h2>
          <span>{records.length.toString().padStart(2, "0")} RECORDS</span>
        </div>
        {loading ? (
          <p className={styles.message}>Loading local evidence…</p>
        ) : error ? (
          <p className={styles.error}>{error}</p>
        ) : records.length === 0 ? (
          <p className={styles.message}>No evidence recorded by this node.</p>
        ) : (
          <div className={styles.tableWrap}>
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Event</th>
                  <th>Type</th>
                  <th>Title</th>
                  <th>Captured</th>
                  <th>File</th>
                </tr>
              </thead>
              <tbody>
                {records.map((record) => (
                  <tr key={record.id}>
                    <td>
                      <strong>{record.evidence_id}</strong>
                      <small>{record.node_id}</small>
                    </td>
                    <td>{record.event_type}</td>
                    <td>{record.evidence_type}</td>
                    <td>{record.title}</td>
                    <td>{new Date(record.captured_at).toLocaleString()}</td>
                    <td>
                      {record.file_name ? (
                        <a
                          href={`${backendUrl}/api/v1/evidence/${record.evidence_id}/file`}
                          target="_blank"
                          rel="noreferrer"
                        >
                          View file
                        </a>
                      ) : (
                        "—"
                      )}
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
