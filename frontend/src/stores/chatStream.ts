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
  appendToken: (delta: string, messageId: string) => void;
  appendThinking: (delta: string, messageId: string) => void;
  setError: (message: string, sessionId: string | null) => void;
  clearActive: (messageId?: string) => void;
  clear: () => void;
}

export const useChatStreamStore = create<ChatStreamState>((set) => ({
  active: null,
  error: null,
  start: (id, sessionId) =>
    set({ active: { id, sessionId, content: "", thinking: "" }, error: null }),
  appendToken: (delta, messageId) =>
    set((s) =>
      s.active && s.active.id === messageId
        ? { active: { ...s.active, content: s.active.content + delta } }
        : s,
    ),
  appendThinking: (delta, messageId) =>
    set((s) =>
      s.active && s.active.id === messageId
        ? { active: { ...s.active, thinking: s.active.thinking + delta } }
        : s,
    ),
  setError: (message, sessionId) => set({ error: { sessionId, message } }),
  clearActive: (messageId) =>
    set((s) => (!messageId || s.active?.id === messageId ? { active: null } : s)),
  clear: () => set({ active: null, error: null }),
}));
