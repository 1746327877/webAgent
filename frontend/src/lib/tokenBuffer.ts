/** 单帧超过该字符数视为高吞吐（设计 09 的 >50 token/ms 按字符近似），启用纯文本降级 */
export const DEGRADE_CHARS_PER_FRAME = 8000;

export interface TokenBatch {
  messageId: string;
  text: string;
  thinking: string;
}

export interface TokenBufferScheduler {
  schedule: (callback: () => void) => number;
  cancel: (handle: number) => void;
}

const defaultScheduler: TokenBufferScheduler = {
  schedule: (callback) =>
    typeof requestAnimationFrame === "function"
      ? requestAnimationFrame(callback)
      : (setTimeout(callback, 16) as unknown as number),
  cancel: (handle) => {
    if (typeof cancelAnimationFrame === "function") cancelAnimationFrame(handle);
    else clearTimeout(handle);
  },
};

export function createTokenBuffer(
  flush: (batch: TokenBatch) => void,
  scheduler: TokenBufferScheduler = defaultScheduler,
) {
  let batch: TokenBatch = { messageId: "", text: "", thinking: "" };
  let frame: number | null = null;
  let degraded = false;

  function cancelFrame() {
    if (frame !== null) {
      scheduler.cancel(frame);
      frame = null;
    }
  }

  function emitBatch() {
    if (!batch.messageId || (!batch.text && !batch.thinking)) return;
    if (batch.text.length + batch.thinking.length >= DEGRADE_CHARS_PER_FRAME) degraded = true;
    const current = batch;
    batch = { messageId: current.messageId, text: "", thinking: "" };
    flush(current);
  }

  return {
    push(kind: "text" | "thinking", delta: string, messageId: string) {
      if (batch.messageId && batch.messageId !== messageId) {
        cancelFrame(); // 换消息先提交旧批，避免内容串台
        emitBatch();
      }
      batch.messageId = messageId;
      if (kind === "text") batch.text += delta;
      else batch.thinking += delta;
      if (frame === null) frame = scheduler.schedule(() => {
        frame = null;
        emitBatch();
      });
    },
    flushNow() {
      cancelFrame();
      emitBatch();
    },
    cancel() {
      cancelFrame();
      batch = { messageId: "", text: "", thinking: "" };
      degraded = false;
    },
    get degraded() {
      return degraded;
    },
  };
}
