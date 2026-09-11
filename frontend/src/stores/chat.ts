import { create } from "zustand";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  thinking: string;
}

interface ChatState {
  messages: ChatMessage[];
  generating: boolean;
  addMessage: (m: ChatMessage) => void;
  appendToken: (delta: string) => void;
  appendThinking: (delta: string) => void;
  setGenerating: (v: boolean) => void;
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  generating: false,
  addMessage: (m) => set((s) => ({ messages: [...s.messages, m] })),
  appendToken: (delta) =>
    set((s) => {
      const msgs = [...s.messages];
      const last = msgs[msgs.length - 1];
      msgs[msgs.length - 1] = { ...last, content: last.content + delta };
      return { messages: msgs };
    }),
  appendThinking: (delta) =>
    set((s) => {
      const msgs = [...s.messages];
      const last = msgs[msgs.length - 1];
      msgs[msgs.length - 1] = { ...last, thinking: last.thinking + delta };
      return { messages: msgs };
    }),
  setGenerating: (v) => set({ generating: v }),
}));
