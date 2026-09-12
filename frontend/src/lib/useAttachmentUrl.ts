import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

/**
 * <img> 无法携带 Bearer 头，因此经 apiFetch 鉴权取 blob 再转 objectURL。
 * id 变化或组件卸载时释放旧 URL，避免内存泄漏。
 */
export function useAttachmentUrl(id: string | undefined): string | null {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    let objectUrl: string | null = null;
    void (async () => {
      try {
        const res = await apiFetch(`/api/v1/attachments/${id}`);
        if (!res.ok) return;
        const blob = await res.blob();
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      } catch {
        // 加载失败时不渲染缩略图，不打断消息展示
      }
    })();
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      setUrl(null);
    };
  }, [id]);

  return url;
}
