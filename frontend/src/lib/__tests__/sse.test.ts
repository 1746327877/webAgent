import { expect, test } from "vitest";
import { parseSSE, type SSEEvent } from "@/lib/sse";

function streamFrom(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      chunks.forEach((c) => controller.enqueue(encoder.encode(c)));
      controller.close();
    },
  });
}

async function collect(stream: ReadableStream<Uint8Array>): Promise<SSEEvent[]> {
  const out: SSEEvent[] = [];
  for await (const e of parseSSE(stream)) out.push(e);
  return out;
}

test("解析单个完整事件", async () => {
  const events = await collect(streamFrom(['event: token\ndata: {"delta": "你好"}\n\n']));
  expect(events).toEqual([{ event: "token", data: { delta: "你好" } }]);
});

test("事件被 chunk 边界切断时仍能解析", async () => {
  const events = await collect(streamFrom(["event: tok", 'en\ndata: {"del', 'ta": "a"}\n\nevent: done\ndata: {}\n\n']));
  expect(events.map((e) => e.event)).toEqual(["token", "done"]);
});

test("一个 chunk 含多个事件", async () => {
  const events = await collect(
    streamFrom(['event: a\ndata: {"x":1}\n\nevent: b\ndata: {"x":2}\n\n']),
  );
  expect(events).toHaveLength(2);
});

test("非 JSON data 原样返回", async () => {
  const events = await collect(streamFrom(["event: raw\ndata: hello\n\n"]));
  expect(events[0].data).toBe("hello");
});
