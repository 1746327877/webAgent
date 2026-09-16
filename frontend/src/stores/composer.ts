import { create } from "zustand";

interface ComposerState {
  /** 用户为后续消息显式选择的模型；null 表示沿用智能体默认 */
  modelOverride: string | null;
  setModelOverride: (model: string | null) => void;
  /** 后续消息是否携带联网搜索工具（部署级配置可用时才允许开启） */
  webSearch: boolean;
  setWebSearch: (enabled: boolean) => void;
}

/**
 * 输入框模型选择：页面级组件状态（非服务端持久化）。
 * 选择后对随后发送的消息生效，会话切换/刷新页面后回落到智能体默认。
 * webSearch 同理：仅对随后发送的消息生效，不持久化。
 */
export const useComposerStore = create<ComposerState>((set) => ({
  modelOverride: null,
  setModelOverride: (modelOverride) => set({ modelOverride }),
  webSearch: false,
  setWebSearch: (webSearch) => set({ webSearch }),
}));
