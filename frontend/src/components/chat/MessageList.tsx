import { Virtuoso } from "react-virtuoso";
import type { MessageItemData } from "@/api/sessions";
import MessageItem from "@/components/chat/MessageItem";
import type { Citation } from "@/lib/citations";
import type { ReactNode } from "react";

interface Props {
  items: MessageItemData[];
  renderActions: (m: MessageItemData) => ReactNode;
  onOpenCitation?: (citation: Citation) => void;
  agentOf?: (m: MessageItemData) => { emoji: string; name: string } | undefined;
  isRelayOf?: (m: MessageItemData) => boolean;
  /** 高吞吐降级：流式 text 块纯文本渲染 */
  degraded?: boolean;
  /** 错误态重试回调（消息 id） */
  onRetry?: (id: string) => void;
}

export default function MessageList({
  items,
  renderActions,
  onOpenCitation,
  agentOf,
  isRelayOf,
  degraded,
  onRetry,
}: Props) {
  return (
    <Virtuoso
      data={items}
      followOutput="smooth"
      computeItemKey={(_, m) => m.id}
      className="min-h-0 flex-1"
      itemContent={(_, m) => (
        <div className="px-4 py-2">
          <MessageItem
            message={m}
            actions={renderActions(m)}
            onOpenCitation={onOpenCitation}
            agent={agentOf?.(m)}
            isRelay={isRelayOf?.(m)}
            degraded={degraded}
            onRetry={onRetry}
          />
        </div>
      )}
    />
  );
}
