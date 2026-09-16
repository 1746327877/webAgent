import { create } from "zustand";
import type { Citation } from "@/lib/citations";

export interface ToolEvent {
  type: "tool_call" | "tool_result";
  id: string;
  tool?: string;
  args?: unknown;
  status?: string;
  elapsed_ms?: number;
  preview?: string;
  /** 工具结果里提取出的 URL（链接 / 图片），供前端直接展示与跳转 */
  links?: string[];
  images?: string[];
}

interface ActiveStream {
  id: string;
  sessionId: string;
  content: string;
  thinking: string;
  citations: Citation[];
  toolEvents: ToolEvent[];
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
  appendCitation: (citation: Citation, messageId?: string) => void;
  appendToolEvent: (event: ToolEvent, messageId?: string) => void;
  setError: (message: string, sessionId: string | null) => void;
  clearActive: (messageId?: string) => void;
  clear: () => void;
}

export const useChatStreamStore = create<ChatStreamState>((set) => ({
  active: null,
  error: null,
  start: (id, sessionId) =>
    set({
      active: { id, sessionId, content: "", thinking: "", citations: [], toolEvents: [] },
      error: null,
    }),
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
  appendCitation: (citation, messageId) =>
    set((s) =>
      s.active && (!messageId || s.active.id === messageId)
        ? { active: { ...s.active, citations: [...s.active.citations, citation] } }
        : s,
    ),
  appendToolEvent: (event, messageId) =>
    set((s) =>
      s.active && (!messageId || s.active.id === messageId)
        ? { active: { ...s.active, toolEvents: [...s.active.toolEvents, event] } }
        : s,
    ),
  setError: (message, sessionId) => set({ error: { sessionId, message } }),
  clearActive: (messageId) =>
    set((s) => (!messageId || s.active?.id === messageId ? { active: null } : s)),
  clear: () => set({ active: null, error: null }),
}));
