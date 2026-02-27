import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "../store/auth";
import { api } from "../api/client";

export default function Dashboard() {
  const { user, setUser, logout } = useAuthStore();
  const navigate = useNavigate();

  useEffect(() => {
    if (!user) {
      api.get("/auth/me")
        .then(({ data }) => setUser(data))
        .catch(() => navigate("/login"));
    }
  }, []);

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
        <span className="font-bold text-gray-900 text-lg">Rastro</span>
        <div className="flex items-center gap-4">
          <span className="text-sm text-gray-500">{user?.email}</span>
          <button onClick={handleLogout} className="text-sm text-gray-500 hover:text-gray-900">
            Salir
          </button>
        </div>
      </header>
      <main className="max-w-2xl mx-auto mt-24 px-6 text-center">
        <h2 className="text-3xl font-bold text-gray-900 mb-3">
          La memoria de tu despacho
        </h2>
        <p className="text-gray-500 mb-10">
          Conecta tu Google Drive y Gmail para empezar a buscar.
        </p>
        <div className="bg-white rounded-2xl border border-gray-200 p-6">
          <p className="text-sm text-gray-400 text-center">
            Próximo paso: conectar integraciones — PRD 2
          </p>
        </div>
      </main>
    </div>
  );
}
