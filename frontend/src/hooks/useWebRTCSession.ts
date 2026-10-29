"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type WebRTCStats = {
  rttMs: number | null;
  packetsReceived: number;
  bytesReceived: number;
  frameWidth: number;
  frameHeight: number;
  fps: number;
};

export type WebRTCSessionState = {
  sessionId: string | null;
  nodeId: string | null;
  incidentId: string | null;
  status: "IDLE" | "REQUESTED" | "SIGNALING" | "CONNECTING" | "CONNECTED" | "ENDED" | "FAILED";
  error: string | null;
  durationSeconds: number;
  stats: WebRTCStats | null;
};

export function useWebRTCSession() {
  const [state, setState] = useState<WebRTCSessionState>({
    sessionId: null,
    nodeId: null,
    incidentId: null,
    status: "IDLE",
    error: null,
    durationSeconds: 0,
    stats: null,
  });

  const [stream, setStream] = useState<MediaStream | null>(null);

  const pcRef = useRef<RTCPeerConnection | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const statsTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const durationTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const activeSessionIdRef = useRef<string | null>(null);
  const activeNodeUrlRef = useRef<string | null>(null); // URL of the node that owns the active session

  const cleanup = useCallback(() => {
    if (statsTimerRef.current) {
      clearInterval(statsTimerRef.current);
      statsTimerRef.current = null;
    }
    if (durationTimerRef.current) {
      clearInterval(durationTimerRef.current);
      durationTimerRef.current = null;
    }
    if (wsRef.current) {
      try {
        wsRef.current.close();
      } catch {
        // ignore
      }
      wsRef.current = null;
    }
    if (pcRef.current) {
      try {
        pcRef.current.close();
      } catch {
        // ignore
      }
      pcRef.current = null;
    }
    setStream(null);
  }, []);

  const stopSession = useCallback(async () => {
    const sid = activeSessionIdRef.current;
    const nodeUrl = activeNodeUrlRef.current;
    if (sid) {
      try {
        // Stop the session on the correct node (same one that owns the session)
        const stopBase = nodeUrl ?? (process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000");
        await fetch(`${stopBase}/api/v1/webrtc/sessions/${sid}/stop`, {
          method: "POST",
        });
      } catch {
        // ignore
      }
    }
    cleanup();
    setState((prev) => ({
      ...prev,
      status: "ENDED",
    }));
    activeSessionIdRef.current = null;
    activeNodeUrlRef.current = null;
  }, [cleanup]);

  const startSession = useCallback(
    async (
      nodeId: string,
      incidentId?: string,
      options: { video?: boolean; audio?: boolean } = { video: true, audio: true },
      nodeBaseUrl?: string, // The specific node's HTTP base URL, e.g. http://localhost:8001
    ) => {
      cleanup();

      setState({
        sessionId: null,
        nodeId,
        incidentId: incidentId || null,
        status: "REQUESTED",
        error: null,
        durationSeconds: 0,
        stats: null,
      });

      try {
        const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

        // Route session creation to the target node directly when nodeBaseUrl is provided.
        // This is critical: the session (aiortc PeerConnection) and the signaling WebSocket
        // MUST live in the same process. If we POST to backend:8000 but the session ends up
        // on node-a:8001 (via proxy), the WS to backend:8000 cannot find it.
        // Solution: send BOTH the POST and the WS to the same node URL.
        const sessionCreateUrl = nodeBaseUrl ?? backendUrl;

        // 1. Request WebRTC session — goes directly to the target node
        const res = await fetch(`${sessionCreateUrl}/api/v1/webrtc/sessions`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            node_id: nodeId,
            incident_id: incidentId || null,
            media: {
              video: options.video ?? true,
              audio: options.audio ?? true,
            },
          }),
        });

        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          throw new Error(errData.detail || `Failed to create session (${res.status})`);
        }

        const sessionData = await res.json();
        const sessionId = sessionData.session_id;
        activeSessionIdRef.current = sessionId;
        activeNodeUrlRef.current = sessionCreateUrl; // remember which node owns this session

        setState((prev) => ({
          ...prev,
          sessionId,
          status: "SIGNALING",
        }));

        // 2. Initialize RTCPeerConnection
        const pc = new RTCPeerConnection({
          iceServers: [{ urls: "stun:stun.l.google.com:19302" }],
        });
        pcRef.current = pc;

        // Configure transceivers to receive media
        if (options.video !== false) {
          pc.addTransceiver("video", { direction: "recvonly" });
        }
        if (options.audio !== false) {
          pc.addTransceiver("audio", { direction: "recvonly" });
        }

        const remoteStream = new MediaStream();

        pc.ontrack = (event) => {
          if (event.streams && event.streams[0]) {
            setStream(event.streams[0]);
          } else {
            remoteStream.addTrack(event.track);
            setStream(new MediaStream(remoteStream.getTracks()));
          }
        };

        pc.onconnectionstatechange = () => {
          const state = pc.connectionState;
          if (state === "connected") {
            setState((prev) => ({ ...prev, status: "CONNECTED" }));

            // Start duration timer
            durationTimerRef.current = setInterval(() => {
              setState((prev) => ({ ...prev, durationSeconds: prev.durationSeconds + 1 }));
            }, 1000);

            // Start stats polling timer
            statsTimerRef.current = setInterval(async () => {
              if (pc.connectionState !== "connected") return;
              try {
                const statsReport = await pc.getStats();
                let rtt: number | null = null;
                let packets = 0;
                let bytes = 0;
                let width = 640;
                let height = 480;
                let fps = 25;

                statsReport.forEach((report) => {
                  if (report.type === "candidate-pair" && report.state === "succeeded") {
                    rtt = report.currentRoundTripTime
                      ? Math.round(report.currentRoundTripTime * 1000)
                      : null;
                  }
                  if (report.type === "inbound-rtp" && report.kind === "video") {
                    packets = report.packetsReceived || 0;
                    bytes = report.bytesReceived || 0;
                    if (report.frameWidth) width = report.frameWidth;
                    if (report.frameHeight) height = report.frameHeight;
                    if (report.framesPerSecond) fps = Math.round(report.framesPerSecond);
                  }
                });

                setState((prev) => ({
                  ...prev,
                  stats: {
                    rttMs: rtt,
                    packetsReceived: packets,
                    bytesReceived: bytes,
                    frameWidth: width,
                    frameHeight: height,
                    fps: fps,
                  },
                }));
              } catch {
                // ignore
              }
            }, 1000);
          } else if (state === "failed" || state === "closed") {
            setState((prev) => ({
              ...prev,
              status: state === "failed" ? "FAILED" : "ENDED",
              error: state === "failed" ? "WebRTC connection failed." : null,
            }));
          }
        };

        // 3. Connect to dedicated signaling WebSocket
        // Use the node's own base URL if provided (so the WS goes to the right
        // node process where the aiortc PeerConnection lives).
        const signalingBase = nodeBaseUrl || backendUrl;
        const wsProtocol = signalingBase.startsWith("https") ? "wss" : "ws";
        const host = signalingBase.replace(/^https?:\/\//, "");
        const wsUrl = `${wsProtocol}://${host}/ws/webrtc/${sessionId}`;

        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = async () => {
          setState((prev) => ({ ...prev, status: "CONNECTING" }));

          // Handle ICE candidates
          pc.onicecandidate = (event) => {
            if (event.candidate && ws.readyState === WebSocket.OPEN) {
              ws.send(
                JSON.stringify({
                  type: "ice_candidate",
                  session_id: sessionId,
                  candidate: event.candidate.toJSON(),
                })
              );
            }
          };

          // Create local offer and start gathering
          const offer = await pc.createOffer();
          await pc.setLocalDescription(offer);

          // Wait for initial ICE candidate gathering to complete (or max 1.2s timeout)
          await new Promise<void>((resolve) => {
            if (pc.iceGatheringState === "complete") {
              resolve();
            } else {
              const checkState = () => {
                if (pc.iceGatheringState === "complete") {
                  pc.removeEventListener("icegatheringstatechange", checkState);
                  resolve();
                }
              };
              pc.addEventListener("icegatheringstatechange", checkState);
              setTimeout(resolve, 1200);
            }
          });

          if (ws.readyState === WebSocket.OPEN) {
            ws.send(
              JSON.stringify({
                type: "offer",
                session_id: sessionId,
                sdp: pc.localDescription?.sdp || offer.sdp,
              })
            );
          }
        };

        ws.onmessage = async (event) => {
          try {
            const msg = JSON.parse(event.data);
            if (msg.type === "answer" && msg.sdp) {
              await pc.setRemoteDescription(
                new RTCSessionDescription({
                  type: "answer",
                  sdp: msg.sdp,
                })
              );
            } else if (msg.type === "ice_candidate" && msg.candidate) {
              await pc.addIceCandidate(new RTCIceCandidate(msg.candidate));
            } else if (msg.type === "error") {
              setState((prev) => ({
                ...prev,
                status: "FAILED",
                error: msg.error || "Signaling error",
              }));
            } else if (msg.type === "session_ended") {
              setState((prev) => ({ ...prev, status: "ENDED" }));
              cleanup();
            }
          } catch (err) {
            console.error("Error processing signaling message:", err);
          }
        };

        ws.onerror = () => {
          setState((prev) => ({
            ...prev,
            status: "FAILED",
            error: "Signaling WebSocket connection failed.",
          }));
        };

        ws.onclose = () => {
          if (pc.connectionState !== "connected") {
            setState((prev) => {
              if (prev.status === "CONNECTING" || prev.status === "SIGNALING") {
                return { ...prev, status: "FAILED", error: "Signaling closed unexpectedly." };
              }
              return prev;
            });
          }
        };
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Failed to initiate WebRTC session";
        setState((prev) => ({
          ...prev,
          status: "FAILED",
          error: msg,
        }));
        cleanup();
      }
    },
    [cleanup]
  );

  useEffect(() => {
    return () => {
      cleanup();
    };
  }, [cleanup]);

  return {
    state,
    stream,
    startSession,
    stopSession,
  };
}
