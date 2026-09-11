import type { MessageItemData } from "@/api/sessions";
import BlockRenderer from "@/components/chat/BlockRenderer";

export default function MessageItem({ message }: { message: MessageItemData }) {
  if (message.role === "user") {
    const text = message.blocks.find((b) => b.type === "text")?.content ?? "";
    return (
      <div className="flex justify-end">
        <span className="max-w-[80%] rounded-lg bg-primary px-3 py-2 text-primary-foreground">
          {text}
        </span>
      </div>
    );
  }
  return (
    <div className="space-y-1">
      {message.blocks.map((b, i) => (
        <BlockRenderer key={i} block={b} />
      ))}
    </div>
  );
}
