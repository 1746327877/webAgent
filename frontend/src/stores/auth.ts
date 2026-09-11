import { create } from "zustand";

interface AuthState {
  accessToken: string | null;
  setToken: (token: string) => void;
  clear: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  setToken: (token) => set({ accessToken: token }),
  clear: () => set({ accessToken: null }),
}));
