import { create } from "zustand";

interface ActiveStream {
  id: string;
  sessionId: string;
  content: string;
  thinking: string;
}

interface ChatStreamError {
  sessionId: string | null;
  message: string;
}

interface ChatStreamState {
  active: ActiveStream | null;
  error: ChatStreamError | null;
  start: (id: string, sessionId: string) => void;
  appendToken: (delta: string) => void;
  appendThinking: (delta: string) => void;
  setError: (message: string, sessionId: string | null) => void;
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
  setError: (message, sessionId) => set({ error: { sessionId, message } }),
  clearActive: () => set({ active: null }),
  clear: () => set({ active: null, error: null }),
}));
