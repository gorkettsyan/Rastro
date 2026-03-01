import { Outlet, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "../store/auth";
import Sidebar from "./Sidebar";
import MemoryBadge from "./MemoryBadge";
import LanguageSwitcher from "./LanguageSwitcher";

export default function AppLayout() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { user, logout } = useAuthStore();

  return (
    <div className="r-app">
      <Sidebar />
      <div className="r-app-content">
        <header className="r-topbar">
          <div className="r-topbar-right">
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
        </header>
        <div className="r-app-body">
          <Outlet />
        </div>
      </div>
    </div>
  );
}
