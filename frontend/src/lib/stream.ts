import { apiFetch } from "@/lib/api";
import { parseSSE, type SSEEvent } from "@/lib/sse";

export async function streamRequest(
  path: string,
  body: unknown,
  onEvent: (e: SSEEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await apiFetch(path, { method: "POST", body: JSON.stringify(body), signal });
  if (!res.ok || !res.body) {
    const detail = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(detail.detail ?? `HTTP ${res.status}`);
  }
  for await (const e of parseSSE(res.body)) onEvent(e);
}
