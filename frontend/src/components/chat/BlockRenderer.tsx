import type { Block } from "@/api/sessions";
import MarkdownContent from "@/components/chat/MarkdownContent";

export default function BlockRenderer({ block }: { block: Block }) {
  if (block.type === "thinking") {
    return (
      <details className="mb-1 rounded border px-3 py-2 text-sm text-muted-foreground">
        <summary>思考过程{block.duration_ms ? `（${Math.round(block.duration_ms / 1000)}s）` : ""}</summary>
        <p className="mt-1 whitespace-pre-wrap">{block.content}</p>
      </details>
    );
  }
  if (block.type === "text") {
    return <MarkdownContent content={block.content ?? ""} />;
  }
  if (block.type === "tool_call") {
    return (
      <div className="my-1 rounded border border-dashed px-3 py-2 text-xs text-muted-foreground">
        🔧 调用工具 <span className="font-mono">{String(block.tool)}</span>
        {block.args && block.args !== "{}" ? <span className="ml-1 opacity-70">{String(block.args)}</span> : null}
      </div>
    );
  }
  if (block.type === "tool_result") {
    const ok = block.status === "ok";
    return (
      <details className="my-1 rounded border px-3 py-2 text-xs">
        <summary className="cursor-pointer text-muted-foreground">
          {ok ? "✅" : "⚠️"} {String(block.tool)} · {String(block.elapsed_ms ?? "")}ms
          {!ok ? " · 失败" : ""}
        </summary>
        <p className="mt-1 whitespace-pre-wrap opacity-80">{String(block.preview ?? "")}</p>
      </details>
    );
  }
  return null; // citation 等未知块忽略
}
