"use client";

import { useEffect, useRef, useState } from "react";
import { useWebRTCSession } from "../hooks/useWebRTCSession";
import styles from "./LiveWebRTCFeed.module.css";

export type LiveWebRTCFeedProps = {
  nodeId?: string;
  incidentId?: string;
  autoStart?: boolean;
};

type NodeEntry = {
  node_id: string;
  node_name: string;
  status: string;
  host: string;
  port: number;
};

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

/**
 * Derive the WebRTC base URL for a node.
 *
 * Strategy (in priority order):
 *  1. If the DB has host="localhost" and a port: use http://localhost:{port}  ← correct
 *  2. If the DB has host="node-a" etc (Docker internal): ignore and use port only
 *  3. Fallback: use NEXT_PUBLIC_BACKEND_URL (coordinator at 8000)
 *
 * This guards against stale seed data where host is a Docker service name
 * instead of localhost.
 */
function deriveNodeBaseUrl(node: NodeEntry | undefined): string {
  if (!node) return BACKEND_URL;
  // If host is a Docker-internal service name (not accessible from browser),
  // ignore it and derive the URL from the known port mapping.
  const isDockerInternal =
    node.host !== "localhost" &&
    node.host !== "127.0.0.1" &&
    !node.host.startsWith("192.168.") &&
    !node.host.match(/^\d+\.\d+\.\d+\.\d+$/);
  if (isDockerInternal) {
    // Fall back to localhost:{port} — works when Docker publishes the port
    return `http://localhost:${node.port}`;
  }
  return `http://${node.host}:${node.port}`;
}

export default function LiveWebRTCFeed({
  nodeId = "CCTV-A",
  incidentId = "INC-000001",
  autoStart = false,
}: LiveWebRTCFeedProps) {
  const [selectedNode, setSelectedNode] = useState(nodeId);
  const [nodes, setNodes] = useState<NodeEntry[]>([]);
  const [nodesLoaded, setNodesLoaded] = useState(false);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const autoStartFiredRef = useRef(false);

  const { state, stream, startSession, stopSession } = useWebRTCSession();

  // Fetch registered nodes with their host:port so we can route correctly
  useEffect(() => {
    fetch(`${BACKEND_URL}/api/v1/nodes`)
      .then((r) => r.json())
      .then((list: NodeEntry[]) => {
        setNodes(list);
        setNodesLoaded(true);
        // If the default nodeId exists in the list, keep it; otherwise pick first
        if (!list.find((n) => n.node_id === nodeId) && list.length > 0) {
          setSelectedNode(list[0].node_id);
        }
      })
      .catch(() => {
        setNodesLoaded(true); // still allow start even if node list fails
      });
  }, [nodeId]);

  const getSelectedNodeEntry = (): NodeEntry | undefined =>
    nodes.find((n) => n.node_id === selectedNode);

  const handleStart = () => {
    const nodeEntry = getSelectedNodeEntry();
    const nodeBaseUrl = deriveNodeBaseUrl(nodeEntry);
    console.log(
      `[WebRTC] Starting session: node=${selectedNode} url=${nodeBaseUrl}`
    );
    void startSession(
      selectedNode,
      incidentId,
      { video: true, audio: true },
      nodeBaseUrl
    );
  };

  // Auto-start only once after nodes are loaded
  useEffect(() => {
    if (autoStart && nodesLoaded && !autoStartFiredRef.current) {
      autoStartFiredRef.current = true;
      handleStart();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoStart, nodesLoaded]);

  useEffect(() => {
    if (videoRef.current && stream) {
      videoRef.current.srcObject = stream;
    }
  }, [stream]);

  const isLive = state.status === "CONNECTED";
  const isLoading =
    state.status === "REQUESTED" ||
    state.status === "SIGNALING" ||
    state.status === "CONNECTING";

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div className={styles.titleInfo}>
          <span
            className={
              styles.liveDot + " " + (isLive ? styles.liveActive : styles.liveInactive)
            }
          />
          <h3 className={styles.title}>Tactical Live Video Stream</h3>
          <span className={styles.protocolBadge}>WebRTC · 25 FPS RTP</span>
        </div>

        <div className={styles.controls}>
          <select
            className={styles.nodeSelect}
            value={selectedNode}
            onChange={(e) => setSelectedNode(e.target.value)}
            disabled={isLive || isLoading}
          >
            {nodes.length > 0 ? (
              nodes.map((n) => (
                <option key={n.node_id} value={n.node_id}>
                  {n.node_id} — {n.node_name} ({n.status})
                </option>
              ))
            ) : (
              <option value={selectedNode}>{selectedNode}</option>
            )}
          </select>

          {isLive ? (
            <button className={styles.stopBtn} onClick={() => void stopSession()}>
              ⏹ Stop Stream
            </button>
          ) : (
            <button
              className={styles.startBtn}
              onClick={handleStart}
              disabled={isLoading}
            >
              {isLoading ? "Negotiating SDP..." : "▶ Start Live Stream"}
            </button>
          )}
        </div>
      </div>

      {/* Video Viewport */}
      <div className={styles.viewport}>
        {stream ? (
          <video
            ref={videoRef}
            autoPlay
            playsInline
            muted
            className={styles.videoElement}
          />
        ) : (
          <div className={styles.placeholder}>
            <div className={styles.placeholderIcon}>📹</div>
            <p className={styles.placeholderText}>
              {isLoading
                ? "Establishing low-latency WebRTC peer connection (SDP Offer/Answer & ICE)..."
                : `Camera feed from ${selectedNode} standby. Click "Start Live Stream" to connect.`}
            </p>
            {state.error && <p className={styles.errorText}>⚠ {state.error}</p>}
          </div>
        )}

        {/* Live Overlay Stats */}
        {isLive && (
          <div className={styles.streamOverlay}>
            <span className={styles.overlayBadge}>● LIVE FEED: {selectedNode}</span>
            <span className={styles.overlayMetric}>⏱ {state.durationSeconds}s</span>
            {state.stats?.fps !== undefined && (
              <span className={styles.overlayMetric}>⚡ {state.stats.fps} FPS</span>
            )}
            {state.stats?.rttMs !== null && state.stats?.rttMs !== undefined && (
              <span className={styles.overlayMetric}>📶 {state.stats.rttMs} ms RTT</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
