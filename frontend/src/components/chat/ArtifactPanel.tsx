import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { Button } from "@/components/ui/button";
import MarkdownContent from "@/components/chat/MarkdownContent";
import { apiFetch } from "@/lib/api";
import {
  artifactFileUrl,
  artifactPreviewUrl,
  downloadArtifact,
  useArtifacts,
  type ArtifactInfo,
} from "@/api/artifacts";

/** 与后端 app/ai/convert.DOCX_MIME 一致：docx 不能原生预览，走后端转 HTML */
const DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

// 产物区拖拽宽度：默认 w-96（384px），钳制范围避免挤占对话区，落盘持久化
const PANEL_WIDTH_KEY = "artifact-panel-width";
const PANEL_DEFAULT_WIDTH = 384;
const PANEL_MIN_WIDTH = 280;
const PANEL_MAX_WIDTH = 720;

function clampPanelWidth(value: number): number {
  return Math.min(PANEL_MAX_WIDTH, Math.max(PANEL_MIN_WIDTH, Math.round(value)));
}

function initialPanelWidth(): number {
  const saved = Number(localStorage.getItem(PANEL_WIDTH_KEY));
  if (Number.isFinite(saved) && localStorage.getItem(PANEL_WIDTH_KEY) !== null) {
    return clampPanelWidth(saved);
  }
  return PANEL_DEFAULT_WIDTH;
}

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
  const [width, setWidth] = useState(initialPanelWidth);
  const [dragging, setDragging] = useState(false);
  const dragStart = useRef<{ startX: number; startWidth: number } | null>(null);

  function onHandlePointerDown(e: ReactPointerEvent<HTMLDivElement>) {
    dragStart.current = { startX: e.clientX, startWidth: width };
    setDragging(true);
    // jsdom 没有 setPointerCapture：可选调用避免测试抛错
    e.currentTarget.setPointerCapture?.(e.pointerId);
  }

  useEffect(() => {
    if (!dragging) return;
    // 手柄在面板左边缘：往左拖（clientX 变小）面板变宽
    function onMove(e: PointerEvent) {
      const start = dragStart.current;
      if (start) setWidth(clampPanelWidth(start.startWidth + (start.startX - e.clientX)));
    }
    function onUp() {
      setDragging(false);
      dragStart.current = null;
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
  }, [dragging]);

  // 拖拽结束再落盘，避免 move 高频写 localStorage；挂载时也会写一次默认值，无害
  useEffect(() => {
    if (!dragging) localStorage.setItem(PANEL_WIDTH_KEY, String(width));
  }, [dragging, width]);

  return (
    <aside
      aria-label="会话产物"
      style={{ width }}
      className={`relative flex shrink-0 flex-col overflow-hidden border-l ${dragging ? "select-none" : ""}`}
    >
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="调整产物区宽度"
        data-testid="artifact-resize-handle"
        title="拖拽调整宽度，双击恢复默认"
        onPointerDown={onHandlePointerDown}
        onDoubleClick={() => setWidth(PANEL_DEFAULT_WIDTH)}
        className={`absolute top-0 bottom-0 -left-1 w-2 cursor-col-resize touch-none ${
          dragging ? "bg-primary/40" : "hover:bg-primary/20"
        }`}
      />
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
  const [html, setHtml] = useState<string | null>(null);
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    let created: string | null = null;
    setText(null);
    setHtml(null);
    setBlobUrl(null);
    setError(null);

    void (async () => {
      try {
        if (artifact.mime_type === DOCX_MIME) {
          const res = await apiFetch(artifactPreviewUrl(artifact.id));
          if (!res.ok) throw new Error(`加载失败（HTTP ${res.status}）`);
          const body = await res.text();
          if (alive) setHtml(body);
          return;
        }
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
        ) : artifact.mime_type === DOCX_MIME ? (
          html === null ? (
            <p className="text-sm text-muted-foreground">加载中…</p>
          ) : (
            /* sandbox 不含 allow-scripts：docx 转出的 HTML 即使含脚本也不会执行 */
            <iframe
              sandbox=""
              srcDoc={html}
              title={artifact.filename}
              className="h-full min-h-96 w-full"
            />
          )
        ) : artifact.mime_type.startsWith("text/") ? (
          text === null ? (
            <p className="text-sm text-muted-foreground">加载中…</p>
          ) : (
            /* 纪要类 md 的 `## 我` / `## 助手` 渲染成身份徽章框 */
            <MarkdownContent content={text} roleBadges />
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
