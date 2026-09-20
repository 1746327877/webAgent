import { create } from "zustand";

export type Theme = "light" | "dark";
const THEME_KEY = "ui-theme";
const THINKING_KEY = "ui-thinking-open";
const SIDEBAR_KEY = "ui-sidebar-collapsed";

export function applyTheme(theme: Theme): void {
  document.documentElement.classList.toggle("dark", theme === "dark");
  localStorage.setItem(THEME_KEY, theme);
}

function initialTheme(): Theme {
  const saved = localStorage.getItem(THEME_KEY);
  if (saved === "light" || saved === "dark") return saved;
  return typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

interface UiState {
  theme: Theme;
  thinkingDefaultOpen: boolean;
  sidebarCollapsed: boolean;
  toggleTheme: () => void;
  setThinkingDefaultOpen: (open: boolean) => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
}

export const useUiStore = create<UiState>((set, get) => ({
  theme: initialTheme(),
  thinkingDefaultOpen: localStorage.getItem(THINKING_KEY) === "1",
  sidebarCollapsed: localStorage.getItem(SIDEBAR_KEY) === "1",
  toggleTheme: () => {
    const theme: Theme = get().theme === "dark" ? "light" : "dark";
    applyTheme(theme);
    set({ theme });
  },
  setThinkingDefaultOpen: (open) => {
    localStorage.setItem(THINKING_KEY, open ? "1" : "0");
    set({ thinkingDefaultOpen: open });
  },
  setSidebarCollapsed: (collapsed) => {
    localStorage.setItem(SIDEBAR_KEY, collapsed ? "1" : "0");
    set({ sidebarCollapsed: collapsed });
  },
}));
