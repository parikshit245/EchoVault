"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import HeaderNav from "../../components/HeaderNav";
import { useEventStream } from "../../hooks/useEventStream";
import styles from "./page.module.css";

type NodeType = "EVIDENCE" | "SECURITY" | "MOBILE" | "COORDINATOR";
type NodeStatus = "ONLINE" | "OFFLINE" | "UNKNOWN";

type Node = {
  id: string;
  node_id: string;
  node_name: string;
  node_type: NodeType;
  host: string;
  port: number;
  grpc_host: string | null;
  grpc_port: number | null;
  status: NodeStatus;
  description: string | null;
  last_seen_at: string | null;
};

const backendUrl =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

function formatDate(value: string | null): string {
  return value ? new Date(value).toLocaleString() : "Never seen";
}

const statusClass: Record<NodeStatus, string> = {
  ONLINE: styles.online,
  OFFLINE: styles.offline,
  UNKNOWN: styles.unknown,
};

function WsStatusDot({ status }: { status: string }) {
  if (status === "connected")
    return <span className={styles.wsLive} title="WebSocket: Live">● LIVE</span>;
  if (status === "connecting")
    return <span className={styles.wsConnecting} title="WebSocket: Connecting">● CONNECTING</span>;
  return <span className={styles.wsOff} title="WebSocket: Disconnected">● OFFLINE</span>;
}

export default function NodesPage() {
  const [nodes, setNodes] = useState<Node[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [remoteStatus, setRemoteStatus] = useState<Record<string, string>>({});
  // Optimistic status overrides from WebSocket events
  const [statusOverrides, setStatusOverrides] = useState<Record<string, NodeStatus>>({});

  const loadNodes = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch(`${backendUrl}/api/v1/nodes`);
      if (!response.ok) throw new Error("Unable to load registered nodes.");
      const fresh: Node[] = await response.json();
      setNodes(fresh);
      // Clear overrides — fresh data takes precedence
      setStatusOverrides({});
      setError(null);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to load registered nodes.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadNodes();
  }, [loadNodes]);

  // WebSocket — subscribe to node events only
  const { status: wsStatus, events: liveEvents } = useEventStream({
    filters: {
      event_types: ["node.registered", "node.status_changed"],
    },
  });

  // On node.status_changed event: apply optimistic override + schedule refresh
  const lastEventId = liveEvents[0]?.message_id;
  useEffect(() => {
    if (!lastEventId) return;
    const ev = liveEvents[0];
    if (!ev) return;

    if (ev.event_type === "node.status_changed") {
      const nodeId = ev.payload?.node_id as string | undefined;
      const newStatus = ev.payload?.status as NodeStatus | undefined;
      if (nodeId && newStatus) {
        setStatusOverrides((prev) => ({ ...prev, [nodeId]: newStatus }));
      }
    }
    // Refresh from API after a short delay for all node events
    const t = setTimeout(() => void loadNodes(), 1500);
    return () => clearTimeout(t);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastEventId]);

  async function registerNode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    const form = new FormData(event.currentTarget);
    const payload = {
      node_id: form.get("node_id"),
      node_name: form.get("node_name"),
      node_type: form.get("node_type"),
      host: form.get("host"),
      port: Number(form.get("port")),
      grpc_host: form.get("grpc_host") || null,
      grpc_port: form.get("grpc_port") ? Number(form.get("grpc_port")) : null,
      description: form.get("description") || null,
    };
    try {
      const response = await fetch(`${backendUrl}/api/v1/nodes`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        throw new Error(
          typeof detail?.detail === "string"
            ? detail.detail
            : "Node registration failed.",
        );
      }
      event.currentTarget.reset();
      await loadNodes();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Node registration failed.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function checkRemoteStatus(nodeId: string) {
    setRemoteStatus((current) => ({
      ...current,
      [nodeId]: "Requesting via gRPC…",
    }));
    try {
      const response = await fetch(
        `${backendUrl}/api/v1/remote/nodes/${nodeId}/status`,
      );
      const data = await response.json();
      if (!response.ok)
        throw new Error(data.detail ?? "Remote node unavailable");
      setRemoteStatus((current) => ({
        ...current,
        [nodeId]: `${data.status} · remote gRPC response`,
      }));
    } catch (err) {
      setRemoteStatus((current) => ({
        ...current,
        [nodeId]:
          err instanceof Error ? err.message : "Remote node unavailable",
      }));
    }
  }

  return (
    <main className={styles.page}>
      <HeaderNav />

      <section className={styles.hero}>
        <p className={styles.kicker}>DISCOVERY LAYER</p>
        <h1>Nodes</h1>
        <p>
          Track the identity, address, and current state of every EchoVault
          participant. Status updates appear in real time via WebSocket.
        </p>
      </section>

      <section className={styles.content}>
        <div className={styles.panel}>
          <div className={styles.panelHeading}>
            <h2>Register node</h2>
            <span>IDENTITY + ADDRESS</span>
          </div>
          <form className={styles.form} onSubmit={registerNode}>
            <label>
              Node ID
              <input name="node_id" placeholder="CCTV-A" required />
            </label>
            <label>
              Node name
              <input name="node_name" placeholder="CCTV Camera A" required />
            </label>
            <label>
              Type
              <select name="node_type" defaultValue="EVIDENCE">
                <option>EVIDENCE</option>
                <option>SECURITY</option>
                <option>MOBILE</option>
                <option>COORDINATOR</option>
              </select>
            </label>
            <label>
              Host
              <input name="host" placeholder="localhost" required />
            </label>
            <label>
              Port
              <input
                name="port"
                type="number"
                min="1"
                max="65535"
                placeholder="8001"
                required
              />
            </label>
            <label>
              gRPC host
              <input name="grpc_host" placeholder="node-a" />
            </label>
            <label>
              gRPC port
              <input
                name="grpc_port"
                type="number"
                min="1"
                max="65535"
                placeholder="50051"
              />
            </label>
            <label className={styles.wide}>
              Description
              <textarea
                name="description"
                placeholder="Optional node description"
                rows={2}
              />
            </label>
            <button disabled={submitting}>
              {submitting ? "Registering…" : "Register node"}
            </button>
          </form>
        </div>

        <div className={styles.panel}>
          <div className={styles.panelHeading}>
            <h2>Registered nodes</h2>
            <div className={styles.panelHeadingRight}>
              <span>{nodes.length.toString().padStart(2, "0")} DISCOVERED</span>
              <button className={styles.refreshBtn} onClick={() => void loadNodes()}>
                ↺ Refresh
              </button>
            </div>
          </div>

          {/* Live event strip */}
          {liveEvents.length > 0 && (
            <div className={styles.eventStrip}>
              <span className={styles.eventStripDot} />
              Latest:{" "}
              <strong>{liveEvents[0].event_type}</strong>{" "}
              from <strong>{liveEvents[0].source_node_id}</strong>
              {liveEvents[0].latency_ms !== null && (
                <span className={styles.eventStripLatency}>
                  {liveEvents[0].latency_ms}ms
                </span>
              )}
            </div>
          )}

          {loading ? (
            <p className={styles.message}>Loading registry…</p>
          ) : error ? (
            <p className={styles.error}>{error}</p>
          ) : nodes.length === 0 ? (
            <p className={styles.message}>No nodes registered yet.</p>
          ) : (
            <div className={styles.tableWrap}>
              <table>
                <thead>
                  <tr>
                    <th>Identity</th>
                    <th>Type</th>
                    <th>Address</th>
                    <th>Status</th>
                    <th>Last seen</th>
                    <th>RPC</th>
                  </tr>
                </thead>
                <tbody>
                  {nodes.map((node) => {
                    const effectiveStatus = statusOverrides[node.node_id] ?? node.status;
                    return (
                      <tr
                        key={node.id}
                        className={statusOverrides[node.node_id] ? styles.rowUpdated : ""}
                      >
                        <td>
                          <strong>{node.node_id}</strong>
                          <small>{node.node_name}</small>
                        </td>
                        <td>{node.node_type}</td>
                        <td>
                          {node.host}:{node.port}
                        </td>
                        <td>
                          <span
                            className={`${styles.status} ${statusClass[effectiveStatus]}`}
                          >
                            ● {effectiveStatus}
                            {statusOverrides[node.node_id] && (
                              <span className={styles.liveTag}>LIVE</span>
                            )}
                          </span>
                        </td>
                        <td>{formatDate(node.last_seen_at)}</td>
                        <td>
                          <button
                            className={styles.rpcButton}
                            onClick={() => void checkRemoteStatus(node.node_id)}
                          >
                            View status
                          </button>
                          {remoteStatus[node.node_id] && (
                            <small className={styles.rpcResult}>
                              {remoteStatus[node.node_id]}
                            </small>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>
    </main>
  );
}
