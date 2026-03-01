import { Link, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";

const NAV_ITEMS = [
  { key: "nav_dashboard", path: "/", icon: "grid" },
  { key: "nav_chat", path: "/chat", icon: "chat" },
  { key: "nav_obligations", path: "/obligations", icon: "calendar" },
  { key: "nav_clause_comparison", path: "/clause-comparison", icon: "compare" },
  { key: "nav_integrations", path: "/integrations", icon: "plug" },
  { key: "nav_settings", path: "/settings", icon: "gear" },
];

function NavIcon({ icon }: { icon: string }) {
  const props = { width: 18, height: 18, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.5, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };

  switch (icon) {
    case "grid":
      return <svg {...props}><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></svg>;
    case "chat":
      return <svg {...props}><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" /></svg>;
    case "calendar":
      return <svg {...props}><rect x="3" y="4" width="18" height="18" rx="2" /><path d="M16 2v4M8 2v4M3 10h18" /></svg>;
    case "compare":
      return <svg {...props}><path d="M16 3h5v5M8 3H3v5M21 3L14 10M3 3l7 7M16 21h5v-5M8 21H3v-5" /></svg>;
    case "plug":
      return <svg {...props}><path d="M12 22v-5M9 7V2M15 7V2M5 7h14a1 1 0 011 1v3a6 6 0 01-6 6h-4a6 6 0 01-6-6V8a1 1 0 011-1z" /></svg>;
    case "gear":
      return <svg {...props}><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 01-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z" /></svg>;
    default:
      return null;
  }
}

export default function Sidebar() {
  const { t } = useTranslation();
  const location = useLocation();

  const isActive = (path: string) =>
    path === "/" ? location.pathname === "/" : location.pathname.startsWith(path);

  return (
    <aside className="r-sidebar">
      <Link to="/" className="r-sidebar-logo">Rastro</Link>

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
    </aside>
  );
}
