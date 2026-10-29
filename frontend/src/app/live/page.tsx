"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import HeaderNav from "../../components/HeaderNav";
import { useWebRTCSession } from "../../hooks/useWebRTCSession";
import styles from "./page.module.css";

type NodeOption = {
  node_id: string;
  node_name: string;
  node_type: string;
  status: string;
  supports_video: boolean;
  supports_audio: boolean;
  host: string;
  port: number;
};

type PastSession = {
  session_id: string;
  incident_id: string | null;
  source_node_id: string;
  status: string;
  has_video: boolean;
  has_audio: boolean;
  created_at: string;
  started_at: string | null;
  ended_at: string | null;
};

function LiveFeedContent() {
  const searchParams = useSearchParams();
  const initialNodeId = searchParams.get("nodeId") || "CCTV-A";
  const initialIncidentId = searchParams.get("incidentId") || "";

  const [nodes, setNodes] = useState<NodeOption[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState(initialNodeId);
  const [incidentIdInput, setIncidentIdInput] = useState(initialIncidentId);
  const [videoEnabled, setVideoEnabled] = useState(true);
  const [audioEnabled, setAudioEnabled] = useState(true);
  const [pastSessions, setPastSessions] = useState<PastSession[]>([]);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const { state, stream, startSession, stopSession } = useWebRTCSession();

  // Load available nodes & past sessions
  const loadData = async () => {
    try {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
      const [nodesRes, sessionsRes] = await Promise.all([
        fetch(`${backendUrl}/api/v1/nodes`),
        fetch(`${backendUrl}/api/v1/webrtc/sessions?limit=10`),
      ]);
      if (nodesRes.ok) {
        const nodeList = await nodesRes.json();
        setNodes(nodeList);
        if (nodeList.length > 0 && !selectedNodeId) {
          setSelectedNodeId(nodeList[0].node_id);
        }
      }
      if (sessionsRes.ok) {
        setPastSessions(await sessionsRes.json());
      }
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    // Initial data load synchronizes the page with the distributed node registry.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadData();
  }, []);

  // Attach stream to video element
  useEffect(() => {
    if (videoRef.current && stream) {
      videoRef.current.srcObject = stream;
      videoRef.current.play().catch(() => {
        // Autoplay may need user gesture or muted
      });
    }
  }, [stream]);

  const handleStart = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedNodeId) return;
    // Find the selected node's HTTP base URL so signaling WS connects to the right process
    const selectedNode = nodes.find((n) => n.node_id === selectedNodeId);
    const nodeBaseUrl = selectedNode
      ? `http://localhost:${selectedNode.port}`
      : undefined;
    await startSession(
      selectedNodeId,
      incidentIdInput.trim() || undefined,
      { video: videoEnabled, audio: audioEnabled },
      nodeBaseUrl,
    );
    void loadData();
  };

  const handleStop = async () => {
    await stopSession();
    void loadData();
  };

  const formatDuration = (sec: number) => {
    const m = Math.floor(sec / 60)
      .toString()
      .padStart(2, "0");
    const s = (sec % 60).toString().padStart(2, "0");
    return `${m}:${s}`;
  };

  const isConnected = state.status === "CONNECTED";
  const isBusy = state.status === "REQUESTED" || state.status === "SIGNALING" || state.status === "CONNECTING";

  return (
    <main className={styles.page}>
      <HeaderNav />

      <section className={styles.hero}>
        <p className={styles.kicker}>DISTRIBUTED MULTIMEDIA STREAMING</p>
        <h1 className={styles.title}>Live Evidence Node Feed</h1>
        <p className={styles.subtitle}>
          Establish direct, peer-to-peer WebRTC audio/video streams with distributed evidence nodes.
          Signaling is coordinated over dedicated WebSockets, while live video/audio is transported
          directly via RTCPeerConnection.
        </p>
      </section>

      {/* Architecture Separation Banner */}
      <section className={styles.archBanner}>
        <div className={styles.archItem}>
          <span className={styles.archLabel}>WEBRTC (PART 9)</span>
          <span className={styles.archDesc}>Direct RTP/SRTP real-time audio/video transport</span>
        </div>
        <div className={styles.archItem}>
          <span className={styles.archLabel}>WEBSOCKET SIGNALING</span>
          <span className={styles.archDesc}>Dedicated /ws/webrtc/&#123;id&#125; for SDP Offer/Answer &amp; ICE</span>
        </div>
        <div className={styles.archItem}>
          <span className={styles.archLabel}>RABBITMQ (PART 6)</span>
          <span className={styles.archDesc}>Asynchronous session lifecycle audit events (webrtc.*)</span>
        </div>
        <div className={styles.archItem}>
          <span className={styles.archLabel}>GRPC (PART 5)</span>
          <span className={styles.archDesc}>Synchronous inter-node RPC metadata retrieval</span>
        </div>
      </section>

      <div className={styles.mainGrid}>
        {/* Left: Session Controls */}
        <aside className={styles.controlPanel}>
          <div className={styles.panelTitle}>
            <span>Session Control</span>
            <span className={styles.panelTag}>P2P MEDIA</span>
          </div>

          {state.error && <div className={styles.errorBanner}>{state.error}</div>}

          <form onSubmit={handleStart}>
            <div className={styles.formGroup}>
              <label className={styles.label}>Select Evidence Node</label>
              <select
                className={styles.select}
                value={selectedNodeId}
                onChange={(e) => setSelectedNodeId(e.target.value)}
                disabled={isConnected || isBusy}
              >
                {nodes.map((n) => (
                  <option key={n.node_id} value={n.node_id}>
                    {n.node_id} — {n.node_name} ({n.status})
                  </option>
                ))}
              </select>
            </div>

            <div className={styles.formGroup}>
              <label className={styles.label}>Associated Incident (Optional)</label>
              <input
                className={styles.input}
                type="text"
                placeholder="INC-000001"
                value={incidentIdInput}
                onChange={(e) => setIncidentIdInput(e.target.value)}
                disabled={isConnected || isBusy}
              />
            </div>

            <div className={styles.checkGroup}>
              <label className={styles.checkLabel}>
                <input
                  type="checkbox"
                  checked={videoEnabled}
                  onChange={(e) => setVideoEnabled(e.target.checked)}
                  disabled={isConnected || isBusy}
                />
                Video Track
              </label>
              <label className={styles.checkLabel}>
                <input
                  type="checkbox"
                  checked={audioEnabled}
                  onChange={(e) => setAudioEnabled(e.target.checked)}
                  disabled={isConnected || isBusy}
                />
                Audio Track
              </label>
            </div>

            {!isConnected && !isBusy && (
              <button type="submit" className={styles.startBtn}>
                ▶ Start Live WebRTC Session
              </button>
            )}

            {isBusy && (
              <button type="button" className={styles.startBtn} disabled>
                ⏳ Negotiating WebRTC ({state.status})...
              </button>
            )}

            {isConnected && (
              <button type="button" className={styles.stopBtn} onClick={handleStop}>
                ⏹ Stop Live Session
              </button>
            )}
          </form>
        </aside>

        {/* Right: Live Video Stage */}
        <section className={styles.stageWrap}>
          <div className={styles.videoStage}>
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
                <h3 className={styles.placeholderTitle}>
                  {isBusy ? "Establishing WebRTC Peer Connection..." : "No Live Feed Active"}
                </h3>
                <p className={styles.placeholderText}>
                  {isBusy
                    ? "Exchanging SDP offer/answer and ICE candidates over WebSocket signaling channel."
                    : "Select a distributed evidence node and click 'Start Live WebRTC Session' to view live camera telemetry."}
                </p>
              </div>
            )}

            {/* Live Video HUD Top */}
            {(isConnected || isBusy) && (
              <div className={styles.videoHudTop}>
                <div className={styles.hudBadge}>
                  NODE: {state.nodeId || selectedNodeId}
                </div>
                {isConnected ? (
                  <div className={styles.livePill}>
                    <span className={styles.liveDot} />
                    <span>LIVE</span>
                  </div>
                ) : (
                  <div className={styles.hudBadge}>
                    {state.status}
                  </div>
                )}
              </div>
            )}

            {/* Live Video HUD Bottom */}
            {isConnected && (
              <div className={styles.videoHudBottom}>
                <div className={styles.statItem}>
                  <span>Duration:</span>
                  <span className={styles.statVal}>{formatDuration(state.durationSeconds)}</span>
                </div>
                <div className={styles.statItem}>
                  <span>Resolution:</span>
                  <span className={styles.statVal}>
                    {state.stats?.frameWidth || 640}x{state.stats?.frameHeight || 480} @ {state.stats?.fps || 25}fps
                  </span>
                </div>
                <div className={styles.statItem}>
                  <span>Packets:</span>
                  <span className={styles.statVal}>{state.stats?.packetsReceived.toLocaleString() || "—"}</span>
                </div>
                <div className={styles.statItem}>
                  <span>RTT:</span>
                  <span className={styles.statVal}>
                    {state.stats?.rttMs !== null && state.stats?.rttMs !== undefined
                      ? `${state.stats.rttMs} ms`
                      : "Direct Link"}
                  </span>
                </div>
              </div>
            )}
          </div>

          {/* Session Audit History */}
          <div className={styles.historyCard}>
            <div className={styles.panelTitle}>
              <span>Recent WebRTC Multimedia Sessions</span>
              <span className={styles.panelTag}>DB AUDIT</span>
            </div>

            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th className={styles.th}>Session ID</th>
                    <th className={styles.th}>Node</th>
                    <th className={styles.th}>Incident</th>
                    <th className={styles.th}>Tracks</th>
                    <th className={styles.th}>Status</th>
                    <th className={styles.th}>Created At</th>
                  </tr>
                </thead>
                <tbody>
                  {pastSessions.length === 0 ? (
                    <tr>
                      <td colSpan={6} className={styles.td} style={{ textAlign: "center", color: "#6e8299" }}>
                        No WebRTC sessions recorded yet.
                      </td>
                    </tr>
                  ) : (
                    pastSessions.map((s) => (
                      <tr key={s.session_id}>
                        <td className={styles.td} style={{ fontFamily: "monospace", color: "#00d2ff" }}>
                          {s.session_id}
                        </td>
                        <td className={styles.td}>{s.source_node_id}</td>
                        <td className={styles.td}>{s.incident_id || "—"}</td>
                        <td className={styles.td}>
                          {s.has_video && "🎥 Video "}
                          {s.has_audio && "🎙️ Audio"}
                        </td>
                        <td className={styles.td}>
                          <span
                            className={
                              s.status === "CONNECTED"
                                ? styles.statusConnected
                                : s.status === "ENDED"
                                ? styles.statusEnded
                                : s.status === "FAILED"
                                ? styles.statusFailed
                                : styles.statusConnecting
                            }
                          >
                            ● {s.status}
                          </span>
                        </td>
                        <td className={styles.td}>
                          {new Date(s.created_at).toLocaleTimeString()}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}

export default function LiveFeedPage() {
  return (
    <Suspense fallback={<div style={{ padding: "2rem", color: "#fff" }}>Loading Live Feed...</div>}>
      <LiveFeedContent />
    </Suspense>
  );
}
