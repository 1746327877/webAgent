import { expect, test } from "vitest";
import { useChatStreamStore } from "@/stores/chatStream";

test("append 累积 token 与 thinking", () => {
  const s = useChatStreamStore.getState();
  s.clear();
  s.start("m1");
  s.appendToken("你");
  s.appendToken("好");
  s.appendThinking("想");
  const active = useChatStreamStore.getState().active!;
  expect(active).toEqual({ id: "m1", content: "你好", thinking: "想" });
});

test("clear 后 active 为 null", () => {
  useChatStreamStore.getState().start("m1");
  useChatStreamStore.getState().clear();
  expect(useChatStreamStore.getState().active).toBeNull();
});

test("setError 记录错误", () => {
  useChatStreamStore.getState().setError("boom");
  expect(useChatStreamStore.getState().error).toBe("boom");
});
