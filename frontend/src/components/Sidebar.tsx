import { Link, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";

const NAV_ITEMS = [
  { key: "nav_home", path: "/dashboard", count: "" },
  { key: "nav_projects", path: "/projects", count: "" },
  { key: "nav_chat", path: "/chat", count: "AI" },
  { key: "memories", path: "/memory", count: "" },
];

export default function Sidebar() {
  const { t } = useTranslation();
  const location = useLocation();

  const isActive = (path: string) => {
    if (path === "/dashboard") return location.pathname === "/dashboard";
    if (path === "/projects") return location.pathname.startsWith("/projects");
    return location.pathname.startsWith(path);
  };

  return (
    <aside className="r-sidebar">
      <Link to="/dashboard" className="r-sidebar-logo">
        <span style={{ color: "var(--accent)" }}>R</span>
        <span style={{ color: "var(--accent-yellow)" }}>a</span>
        stro
      </Link>

      <nav className="r-sidebar-nav">
        {NAV_ITEMS.map((item) => (
          <Link
            key={item.path}
            to={item.path}
            className={`r-sidebar-item${isActive(item.path) ? " active" : ""}`}
          >
            <span>{t(item.key)}</span>
            {item.count && <span className="r-nav-count">{item.count}</span>}
          </Link>
        ))}
      </nav>

      <div className="r-sidebar-bottom">
        <Link
          to="/settings"
          className="r-sidebar-settings-link"
          style={{
            textDecoration: "none",
            color: "var(--ink-primary)",
            fontFamily: "var(--font-mono)",
            fontSize: "0.75rem",
            letterSpacing: "0.05em",
          }}
        >
          {t("nav_settings")}
        </Link>
        <span
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "0.75rem",
            letterSpacing: "0.05em",
            color: "var(--ink-primary)",
          }}
        >
          v1.0.4
        </span>
      </div>
    </aside>
  );
}
