import { useState } from "react";
import { Check, Copy, Pencil, RotateCcw, ThumbsDown, ThumbsUp } from "lucide-react";
import type { MessageItemData } from "@/api/sessions";

interface Props {
  message: MessageItemData;
  onRegenerate: (id: string) => void;
  onEdit: (id: string, text: string) => void;
  onRate: (id: string, rating: 1 | -1) => void;
}

export default function MessageActions({ message, onRegenerate, onEdit, onRate }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(
    message.blocks.find((b) => b.type === "text")?.content ?? "",
  );
  const [copied, setCopied] = useState(false);

  async function copy() {
    const text = message.blocks
      .filter((b) => b.type === "text")
      .map((b) => b.content ?? "")
      .join("\n");
    try {
      await navigator.clipboard?.writeText(text);
    } catch {
      // 剪贴板不可用（权限/非安全上下文）时降级：不中断渲染
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  const copyLabel = copied ? "已复制" : "复制";

  return (
    <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
      <button
        type="button"
        className="hover:text-foreground"
        aria-label={copyLabel}
        title={copyLabel}
        onClick={copy}
      >
        {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
      </button>
      {message.role === "assistant" && (
        <>
          <button
            type="button"
            className="hover:text-foreground"
            aria-label="重新生成"
            title="重新生成"
            onClick={() => onRegenerate(message.id)}
          >
            <RotateCcw className="size-4" />
          </button>
          <button
            type="button"
            className={message.rating === 1 ? "text-foreground" : "hover:text-foreground"}
            aria-label="有用"
            aria-pressed={message.rating === 1}
            title="有用"
            onClick={() => onRate(message.id, 1)}
          >
            <ThumbsUp className="size-4" />
          </button>
          <button
            type="button"
            className={message.rating === -1 ? "text-foreground" : "hover:text-foreground"}
            aria-label="无用"
            aria-pressed={message.rating === -1}
            title="无用"
            onClick={() => onRate(message.id, -1)}
          >
            <ThumbsDown className="size-4" />
          </button>
        </>
      )}
      {message.role === "user" && !editing && (
        <button
          type="button"
          className="hover:text-foreground"
          aria-label="编辑"
          title="编辑"
          onClick={() => setEditing(true)}
        >
          <Pencil className="size-4" />
        </button>
      )}
      {editing && (
        <span className="flex w-full items-start gap-2">
          <textarea
            className="min-h-16 flex-1 rounded border bg-background p-2 text-sm text-foreground"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
          <button
            type="button"
            className="hover:text-foreground"
            onClick={() => {
              onEdit(message.id, draft);
              setEditing(false);
            }}
          >
            保存并重发
          </button>
          <button type="button" className="hover:text-foreground" onClick={() => setEditing(false)}>
            取消
          </button>
        </span>
      )}
    </div>
  );
}
