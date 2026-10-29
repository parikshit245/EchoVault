"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import styles from "./HeaderNav.module.css";

export default function HeaderNav() {
  const pathname = usePathname();

  const links = [
    { href: "/dashboard", label: "Overview", icon: "⌂" },
    { href: "/incidents", label: "Cases", icon: "▣" },
    { href: "/live", label: "Live operations", icon: "◉" },
    { href: "/evidence", label: "Evidence", icon: "◇" },
    { href: "/messaging", label: "Activity", icon: "≋" },
    { href: "/nodes", label: "Sources", icon: "⌘" },
    { href: "/system", label: "System", icon: "⚙" },
  ];

  return (
    <header className={styles.header}>
      <div className={styles.brandGroup}>
        <Link href="/" className={styles.brand}>
          <span className={styles.brandIcon}>⚡</span>
          <span className={styles.brandTitle}>EchoVault</span>
          <span className={styles.brandBadge}>ENTERPRISE</span>
        </Link>
      </div>

      <nav className={styles.nav}>
        {links.map((link) => {
          const isActive =
            pathname === link.href ||
            (link.href !== "/dashboard" && pathname.startsWith(link.href));
          return (
            <Link
              key={link.href}
              href={link.href}
              className={`${styles.navLink} ${isActive ? styles.activeNavLink : ""}`}
            >
              <span className={styles.linkIcon}>{link.icon}</span>
              <span>{link.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className={styles.rightGroup}>
        <Link href="/incidents/INC-000001" className={styles.missionBtn}>
          <span>
            <i /> Active case · INC-000001
          </span>
        </Link>
      </div>
    </header>
  );
}
