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
        navigate("/");
      })
      .catch(() => navigate("/login"));
  }, []);

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <p className="text-gray-500 text-sm">Iniciando sesión...</p>
    </div>
  );
}
