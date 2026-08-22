import styles from "./page.module.css";

export default function Home() {
  return (
    <div className={styles.page}>
      <div className={styles.glow} aria-hidden="true" />
      <main className={styles.main}>
        <header className={styles.header}>
          <span className={styles.mark}>EV</span>
          <span className={styles.eyebrow}>EVIDENCE NETWORK / 01</span>
        </header>
        <div className={styles.intro}>
          <p className={styles.kicker}>FOUNDATION ONLINE</p>
          <h1>EchoVault</h1>
          <p className={styles.subtitle}>
            Distributed Digital Evidence
            <br />
            Collection &amp; Incident Reconstruction
          </p>
          <div className={styles.status}>
            <span className={styles.statusDot} />
            System initialization successful.
          </div>
        </div>
        <footer className={styles.footer}>
          <span>SECURE BY DESIGN</span>
          <span>NODE SERVICE READY</span>
        </footer>
      </main>
    </div>
  );
}
