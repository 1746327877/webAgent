import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

/**
 * 头像同样经鉴权接口返回，<img> 无法携带 Bearer，因此取 blob 再转 objectURL。
 * `version`（一般传 agent.updated_at）变化时重新拉取，替换头像后自动刷新。
 */
export function useAgentAvatarUrl(agentId: string | undefined, version?: string): string | null {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!agentId) return;
    let cancelled = false;
    let objectUrl: string | null = null;
    void (async () => {
      try {
        const res = await apiFetch(`/api/v1/agents/${agentId}/avatar`);
        if (!res.ok) return;
        const blob = await res.blob();
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      } catch {
        // 拉取失败时不渲染图片，组件回退到"名字首字"
      }
    })();
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      setUrl(null);
    };
  }, [agentId, version]);

  return url;
}
