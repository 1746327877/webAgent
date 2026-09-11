import { useState } from "react";
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

  return (
    <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
      <button type="button" className="hover:text-foreground" onClick={copy}>
        {copied ? "已复制" : "复制"}
      </button>
      {message.role === "assistant" && (
        <>
          <button type="button" className="hover:text-foreground" onClick={() => onRegenerate(message.id)}>
            重新生成
          </button>
          <button type="button" className="hover:text-foreground" onClick={() => onRate(message.id, 1)}>
            有用
          </button>
          <button type="button" className="hover:text-foreground" onClick={() => onRate(message.id, -1)}>
            无用
          </button>
        </>
      )}
      {message.role === "user" && !editing && (
        <button type="button" className="hover:text-foreground" onClick={() => setEditing(true)}>
          编辑
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
