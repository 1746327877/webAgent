import { expect, test, vi } from "vitest";
import { createTokenBuffer, type TokenBatch } from "@/lib/tokenBuffer";

function harness() {
  const frames: Array<() => void> = [];
  const schedule = vi.fn((cb: () => void) => {
    frames.push(cb);
    return frames.length;
  });
  const cancel = vi.fn();
  const flushed: TokenBatch[] = [];
  const buffer = createTokenBuffer((batch) => flushed.push(batch), { schedule, cancel });
  return { buffer, flushed, frames, schedule, cancel };
}

test("同一帧内多次 push 只 flush 一次", () => {
  const { buffer, flushed, frames, schedule } = harness();
  buffer.push("text", "你", "m1");
  buffer.push("text", "好", "m1");
  buffer.push("thinking", "想", "m1");
  expect(schedule).toHaveBeenCalledTimes(1);
  expect(flushed).toHaveLength(0); // 未到帧不提交
  frames[0]();
  expect(flushed).toEqual([{ messageId: "m1", text: "你好", thinking: "想" }]);
});

test("切换 messageId 先 flush 旧批", () => {
  const { buffer, flushed } = harness();
  buffer.push("text", "旧", "m1");
  buffer.push("text", "新", "m2");
  expect(flushed.map((batch) => batch.messageId)).toEqual(["m1"]);
  expect(flushed[0].text).toBe("旧");
});

test("flushNow 取消已排帧并立即提交尾部", () => {
  const { buffer, flushed, cancel, frames } = harness();
  buffer.push("text", "尾", "m1");
  buffer.flushNow();
  expect(cancel).toHaveBeenCalledTimes(1);
  expect(flushed).toEqual([{ messageId: "m1", text: "尾", thinking: "" }]);
  expect(frames).toHaveLength(1); // 已排帧被取消、不重复提交
});

test("单帧超过阈值进入降级", () => {
  const { buffer, frames } = harness();
  buffer.push("text", "长".repeat(8000), "m1");
  frames[0]();
  expect(buffer.degraded).toBe(true);
});
