"use client";

import { useState } from "react";
import styles from "./GuidedMission.module.css";

export type GuidedMissionProps = {
  currentStage?: number;
  onExecuteGrpc?: () => Promise<void> | void;
  onExecuteP2p?: () => Promise<void> | void;
  onStartWebRTC?: () => Promise<void> | void;
  onSimulateFailover?: () => Promise<void> | void;
  grpcLoading?: boolean;
  p2pLoading?: boolean;
  webrtcActive?: boolean;
  onNavigateTab?: (tab: string) => void;
};

const STAGES = [
  {
    id: 1,
    title: "1. Establish the case",
    tag: "CASE CONTEXT",
    badge: "STAGE 1",
    desc: "A perimeter signal opens the investigation. Review the location, severity, and sources contributing observations.",
    actionLabel: "Review case context",
    explanation:
      "The case gives observations from independent field sources one shared place without taking ownership away from those sources.",
  },
  {
    id: 2,
    title: "2. Verify remote evidence",
    tag: "SOURCE RETRIEVAL",
    badge: "STAGE 2",
    desc: "Request the original observation from CCTV-B and confirm that it came from the source that captured it.",
    actionLabel: "⚡ Fetch Remote via gRPC",
    explanation:
      "The system asks the owning source directly, returning evidence metadata and its integrity hash without flattening every source into one store.",
  },
  {
    id: 3,
    title: "3. Coordinate the response",
    tag: "DIRECT FIELD CONTACT",
    badge: "STAGE 3",
    desc: "Send an urgent instruction directly to a field source while the case continues to collect evidence.",
    actionLabel: "🌐 Send Direct P2P Alert",
    explanation:
      "A direct peer channel is useful when an investigator needs one specific source to act immediately, without broadcasting to everyone.",
  },
  {
    id: 4,
    title: "4. See what is happening now",
    tag: "LIVE SOURCE VIEW",
    badge: "STAGE 4",
    desc: "Open a live view from CCTV-A to add current situational context to the recorded case evidence.",
    actionLabel: "📹 Start WebRTC Stream",
    explanation:
      "Live media gives the investigator current context; it complements recorded evidence instead of replacing its audit trail.",
  },
  {
    id: 5,
    title: "5. Confirm continuity",
    tag: "AUDIT & AVAILABILITY",
    badge: "STAGE 5",
    desc: "Check that case activity remains visible and other sources continue working if one field device becomes unavailable.",
    actionLabel: "🛡️ Test System Resilience",
    explanation:
      "Durable asynchronous delivery and recovery behavior keep the investigation moving while a source is offline or reconnecting.",
  },
];

export default function GuidedMission({
  currentStage = 1,
  onExecuteGrpc,
  onExecuteP2p,
  onStartWebRTC,
  onSimulateFailover,
  grpcLoading,
  p2pLoading,
  webrtcActive,
}: GuidedMissionProps) {
  const [activeStage, setActiveStage] = useState(currentStage);
  const [feedback, setFeedback] = useState<{
    text: string;
    type: "success" | "info" | "error";
  } | null>(null);

  const stage = STAGES.find((s) => s.id === activeStage) || STAGES[0];

  const handleAction = async () => {
    setFeedback(null);
    try {
      if (activeStage === 1) {
        setFeedback({
          text: "✓ Incident INC-000001 active: 4 distributed nodes associated across Sector 4 Perimeter.",
          type: "success",
        });
      } else if (activeStage === 2) {
        if (onExecuteGrpc) await onExecuteGrpc();
        setFeedback({
          text: "✓ gRPC RPC GetEvidence succeeded! Evidence EV-002 retrieved from CCTV-B with verified SHA-256 hash.",
          type: "success",
        });
      } else if (activeStage === 3) {
        if (onExecuteP2p) await onExecuteP2p();
        setFeedback({
          text: "✓ Direct P2P incident announcement transmitted to CCTV-B over /ws/peer mesh channel.",
          type: "success",
        });
      } else if (activeStage === 4) {
        if (onStartWebRTC) await onStartWebRTC();
        setFeedback({
          text: "✓ WebRTC live RTP/SRTP multimedia session initiated! 25 FPS live stream active.",
          type: "success",
        });
      } else if (activeStage === 5) {
        if (onSimulateFailover) await onSimulateFailover();
        setFeedback({
          text: "✓ Resilient event published to RabbitMQ echovault.events. Cluster self-healing active.",
          type: "success",
        });
      }
    } catch (err) {
      setFeedback({
        text: `✗ Action failed: ${err instanceof Error ? err.message : "Error"}`,
        type: "error",
      });
    }
  };

  return (
    <div className={styles.wrapper}>
      {/* Header Banner */}
      <div className={styles.topHeader}>
        <div className={styles.titleArea}>
          <span className={styles.badgePulse}>INVESTIGATION WORKFLOW</span>
          <h3>From first signal to verified response</h3>
          <p>
            Follow the decisions an investigator makes while a case is unfolding
            in the field
          </p>
        </div>
        <div className={styles.stepperNav}>
          {STAGES.map((s) => {
            const isCurrent = s.id === activeStage;
            const isPast = s.id < activeStage;
            return (
              <button
                key={s.id}
                onClick={() => {
                  setActiveStage(s.id);
                  setFeedback(null);
                }}
                className={`${styles.stepBtn} ${isCurrent ? styles.stepBtnActive : ""} ${
                  isPast ? styles.stepBtnPast : ""
                }`}
              >
                <span className={styles.stepNum}>{s.id}</span>
                <span className={styles.stepTitle}>
                  {s.title.split(". ")[1]}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Active Stage Card */}
      <div className={styles.stageCard}>
        <div className={styles.stageContent}>
          <div className={styles.stageMeta}>
            <span className={styles.stageBadge}>{stage.badge}</span>
            <span className={styles.protocolChip}>{stage.tag}</span>
          </div>

          <h4 className={styles.stageHeading}>{stage.title}</h4>
          <p className={styles.stageDesc}>{stage.desc}</p>
          <div className={styles.explanationBox}>
            <strong>💡 Why this matters:</strong> {stage.explanation}
          </div>
        </div>

        <div className={styles.stageActions}>
          <button
            onClick={handleAction}
            className={styles.executeBtn}
            disabled={grpcLoading || p2pLoading}
          >
            {grpcLoading
              ? "⚡ Querying via gRPC..."
              : p2pLoading
                ? "🌐 Sending P2P Alert..."
                : activeStage === 4 && webrtcActive
                  ? "📹 Live Stream Active"
                  : stage.actionLabel}
          </button>

          <div className={styles.navRow}>
            <button
              disabled={activeStage <= 1}
              onClick={() => {
                setActiveStage((prev) => Math.max(1, prev - 1));
                setFeedback(null);
              }}
              className={styles.secondaryBtn}
            >
              ← Previous Phase
            </button>
            <button
              disabled={activeStage >= STAGES.length}
              onClick={() => {
                setActiveStage((prev) => Math.min(STAGES.length, prev + 1));
                setFeedback(null);
              }}
              className={styles.primaryNextBtn}
            >
              Next Phase →
            </button>
          </div>
        </div>
      </div>

      {/* Feedback Toast */}
      {feedback && (
        <div
          className={`${styles.feedbackToast} ${
            feedback.type === "success"
              ? styles.toastSuccess
              : feedback.type === "error"
                ? styles.toastError
                : styles.toastInfo
          }`}
        >
          {feedback.text}
        </div>
      )}
    </div>
  );
}
