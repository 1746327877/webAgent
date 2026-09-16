import { useEffect, useState } from "react";
import type { Block } from "@/api/sessions";
import MarkdownContent from "@/components/chat/MarkdownContent";
import { useUiStore } from "@/stores/ui";

export default function BlockRenderer({
  block,
  maxRef = 0,
  onCitation,
  streaming = false,
  degraded = false,
}: {
  block: Block;
  /** 传给 text 分支：本消息已有的最大引用编号 */
  maxRef?: number;
  onCitation?: (ref: number) => void;
  /** 流式输出中：thinking 块自动展开并显示「思考中…」 */
  streaming?: boolean;
  /** 高吞吐降级：text 块跳过 markdown 解析，直接纯文本渲染 */
  degraded?: boolean;
}) {
  const thinkingDefaultOpen = useUiStore((s) => s.thinkingDefaultOpen);
  const [thinkingOpen, setThinkingOpen] = useState(thinkingDefaultOpen);

  useEffect(() => {
    setThinkingOpen(streaming || thinkingDefaultOpen);
  }, [streaming, thinkingDefaultOpen]);

  if (block.type === "thinking") {
    return (
      <details
        open={thinkingOpen}
        onToggle={(e) => setThinkingOpen(e.currentTarget.open)}
        className="mb-1 rounded border px-3 py-2 text-sm text-muted-foreground"
      >
        <summary className="cursor-pointer select-none">
          {streaming ? (
            <span className="animate-pulse">思考中…</span>
          ) : block.duration_ms ? (
            `已深度思考 · 用时 ${(block.duration_ms / 1000).toFixed(1)}s`
          ) : (
            "思考过程"
          )}
        </summary>
        <p className="mt-1 whitespace-pre-wrap">{block.content}</p>
      </details>
    );
  }
  if (block.type === "text") {
    if (degraded) {
      return <p className="whitespace-pre-wrap text-sm">{block.content ?? ""}</p>;
    }
    return (
      <MarkdownContent content={block.content ?? ""} maxRef={maxRef} onCitation={onCitation} />
    );
  }
  if (block.type === "tool_call") {
    const rawArgs = block.args;
    const argsText =
      typeof rawArgs === "string" ? rawArgs : rawArgs ? JSON.stringify(rawArgs) : "";
    return (
      <div className="my-1 rounded border border-dashed px-3 py-2 text-xs text-muted-foreground">
        🔧 调用工具 <span className="font-mono">{String(block.tool)}</span>
        {argsText && argsText !== "{}" ? <span className="ml-1 opacity-70">{argsText}</span> : null}
      </div>
    );
  }
  if (block.type === "tool_result") {
    const ok = block.status === "ok";
    const links = asHttpUrls(block.links);
    const images = asHttpUrls(block.images);
    return (
      <details className="my-1 rounded border px-3 py-2 text-xs">
        <summary className="cursor-pointer text-muted-foreground">
          {ok ? "✅" : "⚠️"} {block.tool ? `${String(block.tool)} · ` : ""}
          {String(block.elapsed_ms ?? "")}ms
          {!ok ? " · 失败" : ""}
        </summary>
        <p className="mt-1 whitespace-pre-wrap opacity-80">{String(block.preview ?? "")}</p>
        {images.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-2">
            {images.map((url) => (
              <a
                key={url}
                href={url}
                target="_blank"
                rel="noreferrer noopener"
                title={`${url}（在新标签页打开）`}
              >
                <img
                  src={url}
                  alt="工具返回图片"
                  loading="lazy"
                  className="h-24 w-24 rounded-md border object-cover"
                />
              </a>
            ))}
          </div>
        )}
        {links.length > 0 && (
          <ul className="mt-2 space-y-0.5">
            {links.map((url) => (
              <li key={url} className="truncate">
                <a
                  href={url}
                  target="_blank"
                  rel="noreferrer noopener"
                  title={`${url}（Ctrl/⌘+点击在新标签页打开）`}
                  className="text-primary hover:underline"
                >
                  🔗 {url}
                </a>
              </li>
            ))}
          </ul>
        )}
      </details>
    );
  }
  return null; // citation 块由 MessageItem 统一渲染为 CitationList
}

/** 只接受 http(s) URL，避免把脏数据/相对路径渲染成可点击链接 */
function asHttpUrls(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter(
    (item): item is string => typeof item === "string" && /^https?:\/\//i.test(item),
  );
}
