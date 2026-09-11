import type { ReactNode } from "react";
import type { MessageItemData } from "@/api/sessions";
import BlockRenderer from "@/components/chat/BlockRenderer";

export default function MessageItem({
  message,
  actions,
}: {
  message: MessageItemData;
  actions?: ReactNode;
}) {
  if (message.role === "user") {
    const text = message.blocks.find((b) => b.type === "text")?.content ?? "";
    return (
      <div className="flex flex-col items-end gap-1">
        <span className="max-w-[80%] rounded-lg bg-primary px-3 py-2 text-primary-foreground">
          {text}
        </span>
        {actions}
      </div>
    );
  }
  return (
    <div className="space-y-1">
      {message.blocks.map((b, i) => (
        <BlockRenderer key={i} block={b} />
      ))}
      {actions}
    </div>
  );
}
