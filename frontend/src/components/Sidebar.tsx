import { Link, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";

const NAV_ITEMS = [
  { key: "nav_home", path: "/dashboard", icon: "home" },
  { key: "nav_projects", path: "/projects", icon: "folder" },
  { key: "nav_chat", path: "/chat", icon: "chat" },
  { key: "memories", path: "/memory", icon: "brain" },
];

function NavIcon({ icon }: { icon: string }) {
  const props = { width: 18, height: 18, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.5, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };

  switch (icon) {
    case "home":
      return <svg {...props}><path d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-4 0a1 1 0 01-1-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 01-1 1h-2z" /></svg>;
    case "folder":
      return <svg {...props}><path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" /></svg>;
    case "chat":
      return <svg {...props}><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" /></svg>;
    case "brain":
      return <svg {...props}><path d="M12 2a7 7 0 017 7c0 2.38-1.19 4.47-3 5.74V17a2 2 0 01-2 2h-4a2 2 0 01-2-2v-2.26C6.19 13.47 5 11.38 5 9a7 7 0 017-7z" /><path d="M10 21h4" /><path d="M9 17h6" /></svg>;
    default:
      return null;
  }
}

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
      <Link to="/dashboard" className="r-sidebar-logo">Rastro</Link>

      <nav className="r-sidebar-nav">
        {NAV_ITEMS.map((item) => (
          <Link
            key={item.path}
            to={item.path}
            className={`r-sidebar-item${isActive(item.path) ? " active" : ""}`}
          >
            <NavIcon icon={item.icon} />
            <span>{t(item.key)}</span>
          </Link>
        ))}
      </nav>

      <div className="r-sidebar-bottom">
        <Link
          to="/settings"
          className={`r-sidebar-item${location.pathname === "/settings" ? " active" : ""}`}
        >
          <svg width={18} height={18} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 01-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z" />
          </svg>
          <span>{t("nav_settings")}</span>
        </Link>
      </div>
    </aside>
  );
}
