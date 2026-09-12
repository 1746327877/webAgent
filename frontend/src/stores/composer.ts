import { create } from "zustand";

interface ComposerState {
  /** 用户为后续消息显式选择的模型；null 表示沿用智能体默认 */
  modelOverride: string | null;
  setModelOverride: (model: string | null) => void;
}

/**
 * 输入框模型选择：页面级组件状态（非服务端持久化）。
 * 选择后对随后发送的消息生效，会话切换/刷新页面后回落到智能体默认。
 */
export const useComposerStore = create<ComposerState>((set) => ({
  modelOverride: null,
  setModelOverride: (modelOverride) => set({ modelOverride }),
}));
