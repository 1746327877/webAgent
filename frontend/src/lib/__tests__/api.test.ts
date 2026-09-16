import { beforeEach, expect, test, vi } from "vitest";
import { apiErrorMessage, apiFetch } from "@/lib/api";
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

test("apiErrorMessage：字符串 detail 原样返回", () => {
  expect(apiErrorMessage({ detail: "会话不存在" }, 404)).toBe("会话不存在");
});

test("apiErrorMessage：FastAPI 校验数组拼成可读文案（不再是 [object Object]）", () => {
  const body = {
    detail: [
      { loc: ["body", "ids"], msg: "List should have at most 1000 items", type: "too_long" },
      { loc: ["body", "ids"], msg: "第二个错误", type: "value_error" },
    ],
  };
  const message = apiErrorMessage(body, 422);
  expect(message).toContain("List should have at most 1000 items");
  expect(message).toContain("第二个错误");
  expect(message).not.toContain("[object Object]");
});

test("apiErrorMessage：无 detail 时回落到状态码", () => {
  expect(apiErrorMessage({}, 500)).toBe("HTTP 500");
  expect(apiErrorMessage(null, 502)).toBe("HTTP 502");
});
