import { useEffect, useRef } from "react";
import { Virtuoso, type VirtuosoHandle } from "react-virtuoso";
import type { MessageItemData } from "@/api/sessions";
import MessageItem from "@/components/chat/MessageItem";
import type { Citation } from "@/lib/citations";
import type { ReactNode } from "react";

interface Props {
  items: MessageItemData[];
  /** 会话标识：切换会话后重新"跳到最底部" */
  sessionKey?: string;
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
  sessionKey,
  renderActions,
  onOpenCitation,
  agentOf,
  isRelayOf,
  degraded,
  onRetry,
}: Props) {
  const virtuosoRef = useRef<VirtuosoHandle>(null);
  // 已对哪个会话执行过"进入即置底"；只执行一次，之后交给 followOutput 跟随流式
  const jumpedForRef = useRef<string | null>(null);

  useEffect(() => {
    if (items.length === 0) return;
    const key = sessionKey ?? "__default__";
    if (jumpedForRef.current === key) return;
    jumpedForRef.current = key;
    // 等 Virtuoso 完成首帧测量再跳，避免目标高度未就绪而落空
    const frame = window.requestAnimationFrame(() => {
      virtuosoRef.current?.scrollToIndex({ index: "LAST", align: "end" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [items.length, sessionKey]);

  return (
    <Virtuoso
      ref={virtuosoRef}
      data={items}
      followOutput="smooth"
      // 首屏就按最后一条起算，减少跳到最底前的"从顶部闪一下"
      initialTopMostItemIndex={Math.max(items.length - 1, 0)}
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
