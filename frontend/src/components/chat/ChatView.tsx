import { useParams } from "react-router-dom";
import { useMessages } from "@/api/sessions";
import MessageItem from "@/components/chat/MessageItem";

export default function ChatView() {
  const { sessionId } = useParams();
  const { data: messages = [] } = useMessages(sessionId);

  if (!sessionId) {
    return (
      <div className="flex flex-1 items-center justify-center text-muted-foreground">
        点击「新建任务」开始对话
      </div>
    );
  }
  return (
    <div className="flex-1 space-y-4 overflow-y-auto p-4">
      {messages.map((m) => (
        <MessageItem key={m.id} message={m} />
      ))}
    </div>
  );
}
