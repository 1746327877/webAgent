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
  if (block.type === "tool_call" || block.type === "tool_result") {
    return (
      <div className="rounded border border-dashed p-2 text-xs text-muted-foreground">
        工具调用（M2 起渲染）
      </div>
    );
  }
  return null; // citation 等未知块忽略
}
