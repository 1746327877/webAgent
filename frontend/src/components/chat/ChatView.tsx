import { useNavigate, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useCreateSession, useMessages, type MessageItemData } from "@/api/sessions";
import { apiFetch } from "@/lib/api";
import { streamRequest } from "@/lib/stream";
import type { SSEEvent } from "@/lib/sse";
import Composer from "@/components/chat/Composer";
import MessageActions from "@/components/chat/MessageActions";
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

  function onStreamEvent(evt: SSEEvent, targetSession: string) {
    if (evt.event === "message_start") {
      start((evt.data as { message_id: string }).message_id, targetSession);
    } else if (evt.event === "token") {
      appendToken((evt.data as { delta: string }).delta);
    } else if (evt.event === "thinking") {
      appendThinking((evt.data as { delta: string }).delta);
    } else if (evt.event === "error") {
      setError((evt.data as { message: string }).message);
    }
  }

  /** 清掉旧流后请求 SSE，结束后清叠加层并刷新消息/会话列表（send 与 regenerate 共用） */
  async function runStream(path: string, body: unknown, targetSession: string, fallbackError: string) {
    clear();
    try {
      await streamRequest(path, body, (evt) => onStreamEvent(evt, targetSession));
    } catch (err) {
      setError(err instanceof Error ? err.message : fallbackError);
    } finally {
      clearActive();
      await queryClient.invalidateQueries({ queryKey: ["messages", targetSession] });
      await queryClient.invalidateQueries({ queryKey: ["sessions"] });
    }
  }

  async function send(text: string) {
    let target = sessionId;
    if (!target) {
      try {
        const created = await createSession.mutateAsync();
        target = created.id;
        navigate(`/sessions/${created.id}`);
      } catch (err) {
        setError(err instanceof Error ? err.message : "发送失败");
        return;
      }
    }
    await runStream(`/api/v1/sessions/${target}/messages`, { content: text }, target, "发送失败");
  }

  async function regenerate(messageId: string) {
    if (!sessionId) return;
    await runStream(
      `/api/v1/sessions/${sessionId}/regenerate`,
      { message_id: messageId },
      sessionId,
      "重新生成失败",
    );
  }

  async function editAndResend(messageId: string, text: string) {
    if (!sessionId) return;
    const res = await apiFetch(`/api/v1/messages/${messageId}`, {
      method: "PATCH",
      body: JSON.stringify({ blocks: [{ type: "text", content: text }] }),
    });
    if (!res.ok) {
      setError(`HTTP ${res.status}`);
      return;
    }
    await regenerate(messageId);
  }

  async function rate(messageId: string, rating: 1 | -1) {
    const res = await apiFetch(`/api/v1/messages/${messageId}`, {
      method: "PATCH",
      body: JSON.stringify({ rating }),
    });
    if (!res.ok) {
      setError(`HTTP ${res.status}`);
      return;
    }
    await queryClient.invalidateQueries({ queryKey: ["messages", sessionId] });
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
          <MessageItem
            key={m.id}
            message={m}
            actions={
              <MessageActions
                message={m}
                onRegenerate={regenerate}
                onEdit={editAndResend}
                onRate={rate}
              />
            }
          />
        ))}
        {streamingMessage && <MessageItem message={streamingMessage} />}
        {error && <p className="text-sm text-red-500">出错：{error}</p>}
      </div>
      <Composer onSend={send} onStop={stop} generating={ownsActive} />
    </>
  );
}
