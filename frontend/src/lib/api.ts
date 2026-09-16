import { useAuthStore } from "@/stores/auth";

let refreshPromise: Promise<boolean> | null = null;

async function refreshOnce(): Promise<boolean> {
  if (!refreshPromise) {
    refreshPromise = (async () => {
      try {
        const res = await fetch("/api/v1/auth/refresh", {
          method: "POST",
          credentials: "include",
        });
        if (!res.ok) return false;
        const data = (await res.json()) as { access_token: string };
        useAuthStore.getState().setToken(data.access_token);
        return true;
      } catch {
        return false;
      } finally {
        setTimeout(() => {
          refreshPromise = null;
        }, 0);
      }
    })();
  }
  return refreshPromise;
}

async function doFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = useAuthStore.getState().accessToken;
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return fetch(path, { ...init, headers, credentials: "include" });
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  let res = await doFetch(path, init);
  if (res.status === 401 && !path.startsWith("/api/v1/auth/")) {
    if (await refreshOnce()) res = await doFetch(path, init);
  }
  return res;
}

/** 把后端的 detail（string / FastAPI 校验数组 / 其它对象）转成可读文案 */
export function apiErrorMessage(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  // FastAPI 422：detail 是 [{ loc, msg, type }]，直接 String() 会得到 [object Object]
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) =>
        item && typeof item === "object" && "msg" in item
          ? String((item as { msg: unknown }).msg)
          : null,
      )
      .filter((text): text is string => Boolean(text));
    if (messages.length > 0) return messages.join("；");
  }
  if (detail != null) {
    try {
      return JSON.stringify(detail);
    } catch {
      // 忽略：退回到状态码文案
    }
  }
  return `HTTP ${status}`;
}

export async function apiJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await apiFetch(path, init);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(apiErrorMessage(body, res.status));
  }
  return (await res.json()) as T;
}

/** 应用启动时静默刷新：Cookie 有效则恢复会话 */
export async function bootstrapAuth(): Promise<void> {
  await refreshOnce();
}
