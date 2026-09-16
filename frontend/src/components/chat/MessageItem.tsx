import type { ReactNode } from "react";
import type { AgentBadge } from "@/api/agents";
import type { Block, MessageItemData } from "@/api/sessions";
import AgentAvatar from "@/components/agents/AgentAvatar";
import BlockRenderer from "@/components/chat/BlockRenderer";
import CitationList from "@/components/chat/CitationList";
import ToolArtifacts from "@/components/chat/ToolArtifacts";
import type { Citation } from "@/lib/citations";
import { useAttachmentUrl } from "@/lib/useAttachmentUrl";

function AttachmentThumb({ id }: { id: string }) {
  const url = useAttachmentUrl(id);
  if (!url) return null;
  return <img src={url} alt="附件图片" className="h-24 w-24 rounded-md object-cover" />;
}

/** 文档附件：不请求 blob / 不渲染 <img>，只展示文件名 chip */
function DocumentChip({ name }: { name: string }) {
  return (
    <span className="flex max-w-64 items-center gap-1.5 rounded-md border bg-muted/40 px-2 py-1 text-xs">
      <span aria-hidden>📄</span>
      <span className="truncate" title={name}>
        {name}
      </span>
    </span>
  );
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
    // block 来自后端 JSON（Block 带索引签名，headings 为 unknown）：非数组（含历史消息缺失）一律兜底为空数组
    headings: Array.isArray(block.headings) ? block.headings.map((h) => String(h)) : [],
  };
}

export default function MessageItem({
  message,
  actions,
  onOpenCitation,
  agent,
  isRelay,
  degraded = false,
  onRetry,
}: {
  message: MessageItemData;
  actions?: ReactNode;
  onOpenCitation?: (citation: Citation) => void;
  agent?: AgentBadge;
  isRelay?: boolean;
  /** 高吞吐降级：流式 text 块纯文本渲染 */
  degraded?: boolean;
  /** 错误态重试：点击「重试」按钮回调消息 id */
  onRetry?: (id: string) => void;
}) {
  if (message.role === "user") {
    const text = message.blocks.find((b) => b.type === "text")?.content ?? "";
    const attachments = message.attachments ?? [];
    return (
      <div className="flex flex-col items-end gap-1">
        {attachments.length > 0 && (
          <div className="flex flex-wrap justify-end gap-1">
            {attachments.map((a) =>
              a.kind === "image" ? (
                <AttachmentThumb key={a.id} id={a.id} />
              ) : (
                <DocumentChip key={a.id} name={a.original_name ?? "附件"} />
              ),
            )}
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
  // 用于判断模型是否已在回复正文里自己给出了图片地址（给了就不重复展示）
  const textContent = message.blocks
    .filter((b) => b.type === "text")
    .map((b) => String(b.content ?? ""))
    .join("\n");
  return (
    <div className="space-y-1">
      {agent && (
        <p className="mb-1 flex items-center gap-1.5 text-xs text-muted-foreground">
          {isRelay ? "接力 · " : ""}
          <AgentAvatar
            agentId={agent.id}
            name={agent.name}
            hasAvatar={agent.has_avatar}
            version={agent.updated_at}
            className="size-4 text-[9px]"
          />
          <span>{agent.name}</span>
        </p>
      )}
      {message.blocks.map((b, i) => {
        if (b.type === "citation") {
          if (i !== firstCitationIndex) return null;
          return (
            <CitationList key="citations" citations={citations} onOpen={onOpenCitation} />
          );
        }
        return <BlockRenderer key={i} block={b} maxRef={maxRef} onCitation={openByRef} streaming={message.status === "streaming"} degraded={degraded && message.status === "streaming"} />;
      })}
      <ToolArtifacts blocks={message.blocks} text={textContent} />
      {message.status === "error" && (
        <p className="text-sm text-red-500">
          生成失败，可点「重新生成」重试
          {onRetry && (
            <button type="button" className="ml-2 underline" onClick={() => onRetry(message.id)}>
              重试
            </button>
          )}
        </p>
      )}
      {message.status === "stopped" && (
        <p className="text-xs text-muted-foreground">已停止</p>
      )}
      {actions}
    </div>
  );
}
