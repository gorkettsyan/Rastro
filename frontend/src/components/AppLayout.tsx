import { useState } from "react";
import { Outlet, useNavigate, useLocation, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "../store/auth";
import Sidebar from "./Sidebar";
import LanguageSwitcher from "./LanguageSwitcher";

export default function AppLayout() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuthStore();
  const [searchQuery, setSearchQuery] = useState("");

  // Detect if we're inside a project view
  const projectMatch = location.pathname.match(/^\/projects\/([^/]+)/);
  const isInProject = projectMatch && projectMatch[1] !== "new";

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const q = searchQuery.trim();
    if (!q) return;
    if (isInProject) {
      navigate(`/search?q=${encodeURIComponent(q)}&project_id=${projectMatch![1]}`);
    } else {
      navigate(`/search?q=${encodeURIComponent(q)}`);
    }
    setSearchQuery("");
  };

  const placeholder = isInProject
    ? t("search_in_project_placeholder")
    : t("search_all_projects_placeholder");

  return (
    <div className="r-app">
      <Sidebar />
      <div className="r-app-content">
        <header className="r-topbar">
          <form onSubmit={handleSearch} className="r-topbar-search">
            <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="var(--ink-muted)" strokeWidth={1.5}>
              <circle cx="11" cy="11" r="8" />
              <path d="M21 21l-4.35-4.35" strokeLinecap="round" />
            </svg>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={placeholder}
              className="r-topbar-search-input"
            />
          </form>
          <div className="r-topbar-right">
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
        </header>
        <div className="r-app-body">
          <Outlet />
        </div>
      </div>
    </div>
  );
}
