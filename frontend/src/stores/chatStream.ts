import { create } from "zustand";

interface ActiveStream {
  id: string;
  sessionId: string;
  content: string;
  thinking: string;
}

interface ChatStreamState {
  active: ActiveStream | null;
  error: string | null;
  start: (id: string, sessionId: string) => void;
  appendToken: (delta: string) => void;
  appendThinking: (delta: string) => void;
  setError: (message: string | null) => void;
  clearActive: () => void;
  clear: () => void;
}

export const useChatStreamStore = create<ChatStreamState>((set) => ({
  active: null,
  error: null,
  start: (id, sessionId) =>
    set({ active: { id, sessionId, content: "", thinking: "" }, error: null }),
  appendToken: (delta) =>
    set((s) => (s.active ? { active: { ...s.active, content: s.active.content + delta } } : s)),
  appendThinking: (delta) =>
    set((s) => (s.active ? { active: { ...s.active, thinking: s.active.thinking + delta } } : s)),
  setError: (message) => set({ error: message }),
  clearActive: () => set({ active: null }),
  clear: () => set({ active: null, error: null }),
}));
