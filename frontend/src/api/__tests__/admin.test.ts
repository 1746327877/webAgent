import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { downloadSpansCsv } from "@/api/admin";

const createObjectURL = vi.fn(() => "blob:spans");
const revokeObjectURL = vi.fn();
const click = vi.fn();

beforeEach(() => {
  createObjectURL.mockClear();
  revokeObjectURL.mockClear();
  click.mockClear();
  vi.useFakeTimers();
  URL.createObjectURL = createObjectURL;
  URL.revokeObjectURL = revokeObjectURL;
  // jsdom 未实现导航：替换 click，避免 blob 下载触发 "Not implemented: navigation"
  HTMLAnchorElement.prototype.click = click;
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

test("导出成功后点击下载并延迟回收 objectURL", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(new Blob(["a,b\r\n"]), { status: 200 })),
  );
  await downloadSpansCsv({ session_id: "s1", status: "ok" });
  expect(createObjectURL).toHaveBeenCalledTimes(1);
  expect(click).toHaveBeenCalledTimes(1);
  // 同步栈内不回收：Firefox/Safari 会因此取消 blob 下载
  expect(revokeObjectURL).not.toHaveBeenCalled();
  vi.runAllTimers();
  expect(revokeObjectURL).toHaveBeenCalledWith("blob:spans");
});

test("导出失败抛出错误且不触发下载", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response("boom", { status: 500 })),
  );
  await expect(downloadSpansCsv({ session_id: "s1" })).rejects.toThrow("导出失败（HTTP 500）");
  expect(createObjectURL).not.toHaveBeenCalled();
  expect(click).not.toHaveBeenCalled();
});
