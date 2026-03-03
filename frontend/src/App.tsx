import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useAuthStore } from "./store/auth";
import Login from "./pages/Login";
import AuthCallback from "./pages/AuthCallback";
import Dashboard from "./pages/Dashboard";
import NewProject from "./pages/NewProject";
import Project from "./pages/Project";
import Chat from "./pages/Chat";
import MemoryPage from "./pages/Memory";
import Integrations from "./pages/Integrations";
import Settings from "./pages/Settings";
import InviteAccept from "./pages/InviteAccept";
import Obligations from "./pages/Obligations";
import ClauseComparison from "./pages/ClauseComparison";
import Search from "./pages/Search";
import Landing from "./pages/Landing";
import AppLayout from "./components/AppLayout";
import ToastContainer from "./components/ToastContainer";

const queryClient = new QueryClient();

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token);
  return token ? <>{children}</> : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<Login />} />
          <Route path="/auth/callback" element={<AuthCallback />} />
          <Route path="/invite/:token" element={<InviteAccept />} />
          <Route element={<PrivateRoute><AppLayout /></PrivateRoute>}>
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/projects/new" element={<NewProject />} />
            <Route path="/projects/:id" element={<Project />} />
            <Route path="/search" element={<Search />} />
            <Route path="/chat" element={<Chat />} />
            <Route path="/chat/:conversationId" element={<Chat />} />
            <Route path="/obligations" element={<Obligations />} />
            <Route path="/clause-comparison" element={<ClauseComparison />} />
            <Route path="/memory" element={<MemoryPage />} />
            <Route path="/integrations" element={<Integrations />} />
            <Route path="/settings" element={<Settings />} />
          </Route>
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </BrowserRouter>
      <ToastContainer />
    </QueryClientProvider>
  );
}
