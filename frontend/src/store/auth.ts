import { create } from "zustand";

interface User {
  id: string;
  email: string;
  full_name: string | null;
  role: string;
  org_id: string;
}

interface AuthState {
  user: User | null;
  token: string | null;
  setToken: (token: string) => void;
  setUser: (user: User) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  token: localStorage.getItem("rastro_token"),
  setToken: (token) => {
    localStorage.setItem("rastro_token", token);
    set({ token });
  },
  setUser: (user) => set({ user }),
  logout: () => {
    localStorage.removeItem("rastro_token");
    set({ user: null, token: null });
  },
}));
