import { Virtuoso } from "react-virtuoso";
import type { MessageItemData } from "@/api/sessions";
import MessageItem from "@/components/chat/MessageItem";
import type { Citation } from "@/lib/citations";
import type { ReactNode } from "react";

interface Props {
  items: MessageItemData[];
  renderActions: (m: MessageItemData) => ReactNode;
  onOpenCitation?: (citation: Citation) => void;
}

export default function MessageList({ items, renderActions, onOpenCitation }: Props) {
  return (
    <Virtuoso
      data={items}
      followOutput="smooth"
      computeItemKey={(_, m) => m.id}
      className="min-h-0 flex-1"
      itemContent={(_, m) => (
        <div className="px-4 py-2">
          <MessageItem message={m} actions={renderActions(m)} onOpenCitation={onOpenCitation} />
        </div>
      )}
    />
  );
}
