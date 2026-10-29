import Link from "next/link";
import styles from "./page.module.css";

export default function Home() {
  return (
    <div className={styles.page}>
      <div className={styles.glow} aria-hidden="true" />
      <main className={styles.main}>
        <header className={styles.header}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
            <span className={styles.mark}>⚡</span>
            <span
              style={{ fontWeight: 800, fontSize: "1.1rem", color: "#fff" }}
            >
              EchoVault
            </span>
            <span className={styles.eyebrow}>INVESTIGATOR WORKSPACE</span>
          </div>
          <div style={{ display: "flex", gap: "0.8rem", alignItems: "center" }}>
            <span
              style={{
                width: "8px",
                height: "8px",
                borderRadius: "50%",
                background: "#22c55e",
                display: "inline-block",
              }}
            />
            <span
              style={{ fontSize: "0.78rem", color: "#86efac", fontWeight: 700 }}
            >
              Secure workspace ready
            </span>
          </div>
        </header>

        <div className={styles.intro}>
          <p className={styles.kicker}>
            DIGITAL INVESTIGATIONS, WITHOUT THE BLIND SPOTS
          </p>
          <h1>Bring every source, observation, and live view into one case.</h1>
          <p className={styles.subtitle}>
            EchoVault gives investigators a clear view of what happened, where
            the evidence came from, and what needs attention next—while cameras,
            sensors, and patrol teams continue working independently in the
            field.
          </p>

          <div
            style={{
              display: "flex",
              gap: "1rem",
              flexWrap: "wrap",
              margin: "2.2rem 0 1.5rem 0",
            }}
          >
            <Link
              href="/incidents/INC-000001"
              style={{
                padding: "0.95rem 1.8rem",
                borderRadius: "10px",
                background: "linear-gradient(135deg, #00d2ff 0%, #0072ff 100%)",
                color: "#ffffff",
                textDecoration: "none",
                fontWeight: 800,
                fontSize: "1rem",
                boxShadow: "0 6px 25px rgba(0, 210, 255, 0.4)",
              }}
            >
              🚨 Open active case →
            </Link>

            <Link
              href="/dashboard"
              style={{
                padding: "0.95rem 1.6rem",
                borderRadius: "10px",
                background: "rgba(255, 255, 255, 0.06)",
                border: "1px solid rgba(255, 255, 255, 0.15)",
                color: "#f8fafc",
                textDecoration: "none",
                fontWeight: 700,
                fontSize: "1rem",
                backdropFilter: "blur(8px)",
              }}
            >
              Go to overview
            </Link>

            <Link
              href="/live"
              style={{
                padding: "0.95rem 1.4rem",
                borderRadius: "10px",
                background: "rgba(255, 255, 255, 0.06)",
                border: "1px solid rgba(255, 255, 255, 0.15)",
                color: "#f8fafc",
                textDecoration: "none",
                fontWeight: 700,
                fontSize: "1rem",
                backdropFilter: "blur(8px)",
              }}
            >
              View live sources
            </Link>
          </div>

          <div className={styles.status}>
            <span className={styles.statusDot} />● 4 evidence sources connected
            · case activity streaming live
          </div>
        </div>

        {/* Feature Highlights Grid */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
            gap: "1.2rem",
            margin: "3rem 0 2rem 0",
            width: "100%",
          }}
        >
          <div
            style={{
              background: "rgba(15, 23, 42, 0.7)",
              border: "1px solid rgba(255,255,255,0.08)",
              padding: "1.2rem",
              borderRadius: "10px",
            }}
          >
            <div style={{ fontSize: "1.4rem", marginBottom: "0.5rem" }}>⚡</div>
            <h3
              style={{
                margin: "0 0 0.3rem 0",
                color: "#f8fafc",
                fontSize: "1rem",
                fontWeight: 700,
              }}
            >
              One case timeline
            </h3>
            <p
              style={{
                margin: 0,
                color: "#94a3b8",
                fontSize: "0.82rem",
                lineHeight: 1.4,
              }}
            >
              See detections, evidence, decisions, and responses together
              instead of searching across disconnected tools.
            </p>
          </div>

          <div
            style={{
              background: "rgba(15, 23, 42, 0.7)",
              border: "1px solid rgba(255,255,255,0.08)",
              padding: "1.2rem",
              borderRadius: "10px",
            }}
          >
            <div style={{ fontSize: "1.4rem", marginBottom: "0.5rem" }}>🌐</div>
            <h3
              style={{
                margin: "0 0 0.3rem 0",
                color: "#f8fafc",
                fontSize: "1rem",
                fontWeight: 700,
              }}
            >
              Source-traceable evidence
            </h3>
            <p
              style={{
                margin: 0,
                color: "#94a3b8",
                fontSize: "0.82rem",
                lineHeight: 1.4,
              }}
            >
              Every item stays connected to the camera, sensor, or patrol source
              that captured it.
            </p>
          </div>

          <div
            style={{
              background: "rgba(15, 23, 42, 0.7)",
              border: "1px solid rgba(255,255,255,0.08)",
              padding: "1.2rem",
              borderRadius: "10px",
            }}
          >
            <div style={{ fontSize: "1.4rem", marginBottom: "0.5rem" }}>📹</div>
            <h3
              style={{
                margin: "0 0 0.3rem 0",
                color: "#f8fafc",
                fontSize: "1rem",
                fontWeight: 700,
              }}
            >
              Live situational awareness
            </h3>
            <p
              style={{
                margin: 0,
                color: "#94a3b8",
                fontSize: "0.82rem",
                lineHeight: 1.4,
              }}
            >
              Open a live camera or bodycam when recorded evidence is not enough
              to make the next decision.
            </p>
          </div>

          <div
            style={{
              background: "rgba(15, 23, 42, 0.7)",
              border: "1px solid rgba(255,255,255,0.08)",
              padding: "1.2rem",
              borderRadius: "10px",
            }}
          >
            <div style={{ fontSize: "1.4rem", marginBottom: "0.5rem" }}>📨</div>
            <h3
              style={{
                margin: "0 0 0.3rem 0",
                color: "#f8fafc",
                fontSize: "1rem",
                fontWeight: 700,
              }}
            >
              Resilient field operations
            </h3>
            <p
              style={{
                margin: 0,
                color: "#94a3b8",
                fontSize: "0.82rem",
                lineHeight: 1.4,
              }}
            >
              Sources can keep working and reporting even when another device or
              network path is temporarily unavailable.
            </p>
          </div>
        </div>

        <footer className={styles.footer}>
          <span>ECHOVAULT · DIGITAL INVESTIGATIONS PLATFORM</span>
          <div style={{ display: "flex", gap: "1.4rem" }}>
            <Link
              href="/dashboard"
              style={{
                color: "#00d2ff",
                textDecoration: "none",
                fontSize: "0.82rem",
                fontWeight: 700,
              }}
            >
              Overview
            </Link>
            <Link
              href="/incidents"
              style={{
                color: "#8da2be",
                textDecoration: "none",
                fontSize: "0.82rem",
              }}
            >
              Cases
            </Link>
            <Link
              href="/evidence"
              style={{
                color: "#8da2be",
                textDecoration: "none",
                fontSize: "0.82rem",
              }}
            >
              Evidence
            </Link>
            <Link
              href="/live"
              style={{
                color: "#8da2be",
                textDecoration: "none",
                fontSize: "0.82rem",
              }}
            >
              Live operations
            </Link>
          </div>
        </footer>
      </main>
    </div>
  );
}
