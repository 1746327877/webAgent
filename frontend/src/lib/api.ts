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
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  return fetch(path, { ...init, headers, credentials: "include" });
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  let res = await doFetch(path, init);
  if (res.status === 401 && !path.startsWith("/api/v1/auth/")) {
    if (await refreshOnce()) res = await doFetch(path, init);
  }
  return res;
}

export async function apiJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await apiFetch(path, init);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail ?? `HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

/** 应用启动时静默刷新：Cookie 有效则恢复会话 */
export async function bootstrapAuth(): Promise<void> {
  await refreshOnce();
}
