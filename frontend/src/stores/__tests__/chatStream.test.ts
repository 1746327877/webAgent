import { expect, test } from "vitest";
import { useChatStreamStore } from "@/stores/chatStream";

test("append 累积 token 与 thinking", () => {
  const s = useChatStreamStore.getState();
  s.clear();
  s.start("m1", "s1");
  s.appendToken("你", "m1");
  s.appendToken("好", "m1");
  s.appendThinking("想", "m1");
  const active = useChatStreamStore.getState().active!;
  expect(active).toEqual({
    id: "m1",
    sessionId: "s1",
    content: "你好",
    thinking: "想",
    citations: [],
    toolEvents: [],
  });
});

test("clear 后 active 为 null", () => {
  useChatStreamStore.getState().start("m1", "s1");
  useChatStreamStore.getState().clear();
  expect(useChatStreamStore.getState().active).toBeNull();
});

test("setError 记录错误及其会话作用域", () => {
  useChatStreamStore.getState().setError("boom", "s1");
  expect(useChatStreamStore.getState().error).toEqual({ sessionId: "s1", message: "boom" });
});

test("clearActive 保留 error，start 重置 error", () => {
  const s = useChatStreamStore.getState();
  s.clear();
  s.start("m1", "s1");
  s.setError("boom", "s1");
  s.clearActive("m1");
  expect(useChatStreamStore.getState().active).toBeNull();
  expect(useChatStreamStore.getState().error).toEqual({ sessionId: "s1", message: "boom" });
  s.setError("boom2", "s2");
  s.start("m2", "s2");
  expect(useChatStreamStore.getState().error).toBeNull();
});

test("不同 messageId 的 append 被忽略", () => {
  const s = useChatStreamStore.getState();
  s.clear();
  s.start("m1", "sess-1");
  s.appendToken("A", "m1");
  s.appendToken("B", "m2"); // 应忽略
  s.appendThinking("C", "m2"); // 应忽略
  const active = useChatStreamStore.getState().active!;
  expect(active.content).toBe("A");
  expect(active.thinking).toBe("");
});

test("clearActive 带 id 守卫：不匹配则不清", () => {
  const s = useChatStreamStore.getState();
  s.clear();
  s.start("m1", "sess-1");
  s.clearActive("m2");
  expect(useChatStreamStore.getState().active?.id).toBe("m1");
  s.clearActive("m1");
  expect(useChatStreamStore.getState().active).toBeNull();
});

test("toolEvents 与 citations 追加", () => {
  const s = useChatStreamStore.getState();
  s.clear();
  s.start("m1", "s1");
  s.appendToolEvent({ type: "tool_call", id: "c1", tool: "time_now", args: {} });
  s.appendCitation({ ref: 1, chunk_id: "c", source: "a.md", page: 2, score: 0.5, snippet: "s" });
  const active = useChatStreamStore.getState().active!;
  expect(active.toolEvents).toHaveLength(1);
  expect(active.citations[0].ref).toBe(1);
});

test("appendCitation/appendToolEvent 的 messageId 守卫", () => {
  const s = useChatStreamStore.getState();
  s.clear();
  s.start("m1", "s1");
  s.appendCitation({ ref: 1, chunk_id: "c", source: "a.md", page: 2, score: 0.5, snippet: "s" }, "m2");
  s.appendToolEvent({ type: "tool_call", id: "c1", tool: "time_now", args: {} }, "m2");
  let active = useChatStreamStore.getState().active!;
  expect(active.citations).toHaveLength(0);
  expect(active.toolEvents).toHaveLength(0);
  s.appendCitation({ ref: 2, chunk_id: "c2", source: "b.md", page: null, score: 0.7, snippet: "s2" }, "m1");
  s.appendToolEvent({ type: "tool_result", id: "c1", status: "ok", elapsed_ms: 3 }, "m1");
  active = useChatStreamStore.getState().active!;
  expect(active.citations.map((c) => c.ref)).toEqual([2]);
  expect(active.toolEvents).toHaveLength(1);
});
