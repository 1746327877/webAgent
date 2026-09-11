import { beforeEach, expect, test, vi } from "vitest";
import { apiFetch } from "@/lib/api";
import { useAuthStore } from "@/stores/auth";

beforeEach(async () => {
  useAuthStore.getState().clear();
  // refreshOnce 的 setTimeout(0) 复位在下一个宏任务执行；等待它跑完，避免单飞状态跨用例泄漏
  await new Promise((resolve) => setTimeout(resolve, 0));
});

test("401 时自动刷新并重试一次", async () => {
  useAuthStore.getState().setToken("old");
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(new Response("", { status: 401 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: "new" }), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);

  const res = await apiFetch("/api/v1/sessions");
  expect(res.status).toBe(200);
  expect(fetchMock).toHaveBeenCalledTimes(3);
  expect(useAuthStore.getState().accessToken).toBe("new");
  vi.unstubAllGlobals();
});

test("并发 401 只触发一次刷新", async () => {
  let refreshed = false;
  let refreshCount = 0;
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    if (String(input).includes("/auth/refresh")) {
      refreshCount += 1;
      refreshed = true;
      return new Response(JSON.stringify({ access_token: "new" }), { status: 200 });
    }
    return refreshed ? new Response("{}", { status: 200 }) : new Response("", { status: 401 });
  });
  vi.stubGlobal("fetch", fetchMock);

  const [a, b] = await Promise.all([apiFetch("/api/v1/sessions"), apiFetch("/api/v1/sessions")]);
  expect(a.status).toBe(200);
  expect(b.status).toBe(200);
  expect(refreshCount).toBe(1);
  vi.unstubAllGlobals();
});

test("刷新失败时原样返回 401", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(new Response("", { status: 401 }))
    .mockResolvedValueOnce(new Response("", { status: 401 }));
  vi.stubGlobal("fetch", fetchMock);

  const res = await apiFetch("/api/v1/sessions");
  expect(res.status).toBe(401);
  expect(fetchMock).toHaveBeenCalledTimes(2);
  vi.unstubAllGlobals();
});
