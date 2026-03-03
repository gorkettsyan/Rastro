import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "../store/auth";
import { api } from "../api/client";

export default function AuthCallback() {
  const navigate = useNavigate();
  const { setToken, setUser } = useAuthStore();

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get("token");

    if (!token) {
      navigate("/login");
      return;
    }

    setToken(token);

    // Fetch user info with the new token
    api.get("/auth/me")
      .then(({ data }) => {
        setUser(data);
        navigate("/dashboard");
      })
      .catch(() => navigate("/login"));
  }, []);

  return (
    <div className="r-login-page">
      <p style={{ fontSize: "15px", color: "var(--ink-muted)" }}>Iniciando sesión...</p>
    </div>
  );
}
