import { Link, useNavigate, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "../store/auth";
import MemoryBadge from "./MemoryBadge";
import LanguageSwitcher from "./LanguageSwitcher";

export default function Header() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuthStore();

  const navItems = [
    { label: t("nav_dashboard"), path: "/" },
    { label: t("nav_chat"), path: "/chat" },
    { label: t("nav_obligations"), path: "/obligations" },
    { label: t("nav_integrations"), path: "/integrations" },
    { label: t("nav_settings"), path: "/settings" },
  ];

  const isActive = (path: string) =>
    path === "/" ? location.pathname === "/" : location.pathname.startsWith(path);

  return (
    <header className="r-header">
      <div className="r-header-inner">
        <Link to="/" className="r-logo">Rastro</Link>
        <nav className="r-nav">
          {navItems.map((item) => (
            <Link
              key={item.path}
              to={item.path}
              className={`r-nav-item${isActive(item.path) ? " active" : ""}`}
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="r-header-right">
          <MemoryBadge />
          <div className="r-header-divider" />
          <LanguageSwitcher />
          <div className="r-header-divider" />
          <span className="r-header-email">{user?.email}</span>
          <button
            className="r-header-signout"
            onClick={() => { logout(); navigate("/login"); }}
          >
            {t("sign_out")}
          </button>
        </div>
      </div>
    </header>
  );
}
