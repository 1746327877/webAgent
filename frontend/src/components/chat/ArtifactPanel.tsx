import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import MarkdownContent from "@/components/chat/MarkdownContent";
import { apiFetch } from "@/lib/api";
import {
  artifactFileUrl,
  downloadArtifact,
  useArtifacts,
  type ArtifactInfo,
} from "@/api/artifacts";

/**
 * 右侧产物区：列出会话产物并预览。
 *
 * 预览走鉴权接口（apiFetch 带 token），因此不能直接把 URL 塞进 iframe/img，
 * 必须先取成 blob/text 再用；离开或切换时释放 objectURL。
 */
export default function ArtifactPanel({
  sessionId,
  onClose,
}: {
  sessionId: string;
  onClose: () => void;
}) {
  const { data: artifacts = [], isLoading } = useArtifacts(sessionId);
  const [activeId, setActiveId] = useState<string | null>(null);
  const active = artifacts.find((item) => item.id === activeId) ?? artifacts[0] ?? null;

  return (
    <aside
      aria-label="会话产物"
      className="flex w-96 shrink-0 flex-col overflow-hidden border-l"
    >
      <div className="flex items-center justify-between border-b px-3 py-2">
        <span className="text-sm font-medium">产物（{artifacts.length}）</span>
        <Button variant="ghost" size="sm" onClick={onClose}>
          关闭
        </Button>
      </div>

      {isLoading ? (
        <p className="p-3 text-sm text-muted-foreground">加载中…</p>
      ) : artifacts.length === 0 ? (
        <p className="p-3 text-sm text-muted-foreground">
          还没有产物。点右上角「导出纪要」把当前会话导出成 Markdown。
        </p>
      ) : (
        <>
          <ul className="max-h-40 shrink-0 overflow-y-auto border-b">
            {artifacts.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => setActiveId(item.id)}
                  className={`w-full truncate px-3 py-1.5 text-left text-sm hover:bg-muted ${
                    active?.id === item.id ? "bg-muted font-medium" : ""
                  }`}
                  title={item.filename}
                >
                  {item.filename}
                  <span className="ml-1 text-xs text-muted-foreground">
                    {formatSize(item.size_bytes)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
          {active && <ArtifactPreview artifact={active} />}
        </>
      )}
    </aside>
  );
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function ArtifactPreview({ artifact }: { artifact: ArtifactInfo }) {
  const [text, setText] = useState<string | null>(null);
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    let created: string | null = null;
    setText(null);
    setBlobUrl(null);
    setError(null);

    void (async () => {
      try {
        const res = await apiFetch(artifactFileUrl(artifact.id));
        if (!res.ok) throw new Error(`加载失败（HTTP ${res.status}）`);
        if (artifact.mime_type.startsWith("text/")) {
          const body = await res.text();
          if (alive) setText(body);
          return;
        }
        const blob = await res.blob();
        created = URL.createObjectURL(blob);
        if (alive) setBlobUrl(created);
      } catch (err) {
        if (alive) setError(err instanceof Error ? err.message : "加载失败");
      }
    })();

    return () => {
      alive = false;
      if (created) URL.revokeObjectURL(created);
    };
  }, [artifact.id, artifact.mime_type]);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center justify-between gap-2 border-b px-3 py-1.5">
        <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground" title={artifact.filename}>
          {artifact.mime_type} · {formatSize(artifact.size_bytes)}
        </span>
        <Button
          variant="outline"
          size="sm"
          onClick={() => void downloadArtifact(artifact)}
        >
          下载
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-3">
        {error ? (
          <p className="text-sm text-red-500">{error}</p>
        ) : artifact.mime_type.startsWith("text/") ? (
          text === null ? (
            <p className="text-sm text-muted-foreground">加载中…</p>
          ) : (
            <MarkdownContent content={text} />
          )
        ) : blobUrl === null ? (
          <p className="text-sm text-muted-foreground">加载中…</p>
        ) : artifact.mime_type === "application/pdf" ? (
          <iframe src={blobUrl} title={artifact.filename} className="h-full min-h-96 w-full" />
        ) : artifact.mime_type.startsWith("image/") ? (
          <img src={blobUrl} alt={artifact.filename} className="max-w-full rounded border" />
        ) : (
          <p className="text-sm text-muted-foreground">
            该类型暂不支持预览，请点「下载」查看。
          </p>
        )}
      </div>
    </div>
  );
}
