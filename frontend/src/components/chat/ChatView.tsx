import { useNavigate, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useCreateSession, useMessages, type MessageItemData } from "@/api/sessions";
import { apiFetch } from "@/lib/api";
import { streamRequest } from "@/lib/stream";
import Composer from "@/components/chat/Composer";
import MessageItem from "@/components/chat/MessageItem";
import { useChatStreamStore } from "@/stores/chatStream";

export default function ChatView() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const createSession = useCreateSession();
  const { data: messages = [] } = useMessages(sessionId);
  const { active, error, start, appendToken, appendThinking, setError, clear, clearActive } =
    useChatStreamStore();
  const ownsActive = Boolean(active && active.sessionId === sessionId);

  async function send(text: string) {
    let target = sessionId;
    try {
      if (!target) {
        const created = await createSession.mutateAsync();
        target = created.id;
        navigate(`/sessions/${created.id}`);
      }
      const targetSession = target;
      clear();
      await streamRequest(`/api/v1/sessions/${targetSession}/messages`, { content: text }, (evt) => {
        if (evt.event === "message_start")
          start((evt.data as { message_id: string }).message_id, targetSession);
        else if (evt.event === "token") appendToken((evt.data as { delta: string }).delta);
        else if (evt.event === "thinking") appendThinking((evt.data as { delta: string }).delta);
        else if (evt.event === "error") setError((evt.data as { message: string }).message);
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "发送失败");
    } finally {
      clearActive();
      await queryClient.invalidateQueries({ queryKey: ["messages", target] });
      await queryClient.invalidateQueries({ queryKey: ["sessions"] });
    }
  }

  async function stop() {
    if (!active || !ownsActive) return;
    await apiFetch(`/api/v1/messages/${active.id}/stop`, { method: "POST" });
  }

  if (!sessionId) {
    return (
      <div className="flex flex-1 items-center justify-center text-muted-foreground">
        点击「新建任务」开始对话
      </div>
    );
  }

  const visible = messages.filter((m) => m.status !== "streaming");
  const streamingMessage: MessageItemData | null =
    ownsActive && active
      ? {
          id: active.id,
          role: "assistant",
          blocks: [
            ...(active.thinking ? [{ type: "thinking", content: active.thinking }] : []),
            { type: "text", content: active.content },
          ],
          status: "streaming",
          rating: null,
          created_at: new Date().toISOString(),
        }
      : null;

  return (
    <>
      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        {visible.map((m) => (
          <MessageItem key={m.id} message={m} />
        ))}
        {streamingMessage && <MessageItem message={streamingMessage} />}
        {error && <p className="text-sm text-red-500">出错：{error}</p>}
      </div>
      <Composer onSend={send} onStop={stop} generating={ownsActive} />
    </>
  );
}
