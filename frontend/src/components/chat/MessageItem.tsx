import type { ReactNode } from "react";
import type { Block, MessageItemData } from "@/api/sessions";
import BlockRenderer from "@/components/chat/BlockRenderer";
import CitationList from "@/components/chat/CitationList";
import type { Citation } from "@/lib/citations";
import { useAttachmentUrl } from "@/lib/useAttachmentUrl";

function AttachmentThumb({ id }: { id: string }) {
  const url = useAttachmentUrl(id);
  if (!url) return null;
  return <img src={url} alt="附件图片" className="h-24 w-24 rounded-md object-cover" />;
}

/** 持久化 citation 块 → Citation（字段缺失时兜底为空串/0，避免渲染崩溃） */
function toCitation(block: Block): Citation {
  const page = block.page;
  return {
    ref: Number(block.ref),
    chunk_id: String(block.chunk_id ?? ""),
    source: String(block.source ?? ""),
    page: page == null ? null : Number(page),
    score: Number(block.score ?? 0),
    snippet: String(block.snippet ?? ""),
  };
}

export default function MessageItem({
  message,
  actions,
  onOpenCitation,
  agent,
  isRelay,
}: {
  message: MessageItemData;
  actions?: ReactNode;
  onOpenCitation?: (citation: Citation) => void;
  agent?: { emoji: string; name: string };
  isRelay?: boolean;
}) {
  if (message.role === "user") {
    const text = message.blocks.find((b) => b.type === "text")?.content ?? "";
    const attachments = message.attachments ?? [];
    return (
      <div className="flex flex-col items-end gap-1">
        {attachments.length > 0 && (
          <div className="flex flex-wrap justify-end gap-1">
            {attachments.map((a) => (
              <AttachmentThumb key={a.id} id={a.id} />
            ))}
          </div>
        )}
        <span className="max-w-[80%] rounded-lg bg-primary px-3 py-2 text-primary-foreground">
          {text}
        </span>
        {actions}
      </div>
    );
  }

  const citations = message.blocks
    .filter((b) => b.type === "citation")
    .map(toCitation);
  const maxRef = citations.reduce((max, c) => Math.max(max, c.ref), 0);
  const openByRef = (ref: number) => {
    const hit = citations.find((c) => c.ref === ref);
    if (hit) onOpenCitation?.(hit);
  };

  const firstCitationIndex = message.blocks.findIndex((b) => b.type === "citation");
  return (
    <div className="space-y-1">
      {agent && (
        <p className="mb-1 text-xs text-muted-foreground">
          {isRelay ? "接力 · " : ""}
          <span>{agent.emoji}</span> {agent.name}
        </p>
      )}
      {message.blocks.map((b, i) => {
        if (b.type === "citation") {
          if (i !== firstCitationIndex) return null;
          return (
            <CitationList key="citations" citations={citations} onOpen={onOpenCitation} />
          );
        }
        return <BlockRenderer key={i} block={b} maxRef={maxRef} onCitation={openByRef} streaming={message.status === "streaming"} />;
      })}
      {message.status === "error" && (
        <p className="text-sm text-red-500">生成失败，可点「重新生成」重试</p>
      )}
      {message.status === "stopped" && (
        <p className="text-xs text-muted-foreground">已停止</p>
      )}
      {actions}
    </div>
  );
}
