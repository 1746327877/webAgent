import { Virtuoso } from "react-virtuoso";
import type { MessageItemData } from "@/api/sessions";
import MessageItem from "@/components/chat/MessageItem";
import type { ReactNode } from "react";

interface Props {
  items: MessageItemData[];
  renderActions: (m: MessageItemData) => ReactNode;
}

export default function MessageList({ items, renderActions }: Props) {
  return (
    <Virtuoso
      data={items}
      followOutput="smooth"
      className="min-h-0 flex-1"
      itemContent={(_, m) => (
        <div className="px-4 py-2">
          <MessageItem message={m} actions={renderActions(m)} />
        </div>
      )}
    />
  );
}
