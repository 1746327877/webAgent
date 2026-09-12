import { useNavigate, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useCreateSession, useMessages, useSession, type MessageItemData } from "@/api/sessions";
import { useAgent } from "@/api/agents";
import { apiFetch } from "@/lib/api";
import { streamRequest } from "@/lib/stream";
import type { SSEEvent } from "@/lib/sse";
import Composer from "@/components/chat/Composer";
import MessageActions from "@/components/chat/MessageActions";
import MessageList from "@/components/chat/MessageList";
import { Button } from "@/components/ui/button";
import { useChatStreamStore } from "@/stores/chatStream";

export default function ChatView() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const createSession = useCreateSession();
  const { data: messages = [] } = useMessages(sessionId);
  const { data: session } = useSession(sessionId);
  const { data: agent } = useAgent(session?.agent_id ?? undefined);
  const { active, error, start, appendToken, appendThinking, setError, clear, clearActive } =
    useChatStreamStore();
  const ownsActive = Boolean(active && active.sessionId === sessionId);
  // 错误只归其产生时的会话：发送创建场景的 error.sessionId 为 null，仅无会话时显示
  const scopedError = error && error.sessionId === (sessionId ?? null) ? error.message : null;

  function onStreamEvent(evt: SSEEvent, targetSession: string) {
    if (evt.event === "message_start") {
      start((evt.data as { message_id: string }).message_id, targetSession);
    } else if (evt.event === "token") {
      const data = evt.data as { delta: string; message_id: string };
      appendToken(data.delta, data.message_id);
    } else if (evt.event === "thinking") {
      const data = evt.data as { delta: string; message_id: string };
      appendThinking(data.delta, data.message_id);
    } else if (evt.event === "error") {
      setError((evt.data as { message: string }).message, targetSession);
    }
  }

  /** 清掉旧流后请求 SSE，结束后清叠加层并刷新消息/会话列表（send 与 regenerate 共用） */
  async function runStream(path: string, body: unknown, targetSession: string, fallbackError: string) {
    clear();
    let streamId: string | undefined;
    try {
      await streamRequest(path, body, (evt) => {
        if (evt.event === "message_start") {
          streamId = (evt.data as { message_id: string }).message_id;
        }
        onStreamEvent(evt, targetSession);
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : fallbackError, targetSession);
    } finally {
      clearActive(streamId);
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
        setError(err instanceof Error ? err.message : "发送失败", target ?? null);
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
      setError(`HTTP ${res.status}`, sessionId);
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
      setError(`HTTP ${res.status}`, sessionId ?? null);
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
      <div className="flex flex-1 flex-col items-center justify-center gap-2 text-muted-foreground">
        {scopedError && <p className="text-sm text-red-500">出错：{scopedError}</p>}
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
          error: null,
          created_at: new Date().toISOString(),
        }
      : null;

  const items = streamingMessage ? [...visible, streamingMessage] : visible;
  // 空会话（无消息、无流式叠加）且有智能体时展示欢迎区
  const showWelcome = messages.length === 0 && !streamingMessage && Boolean(agent);

  return (
    <>
      {agent && (
        <div className="flex items-center gap-2 border-b px-4 py-2 text-sm">
          <span>{agent.emoji}</span>
          <span className="font-medium">{agent.name}</span>
        </div>
      )}
      {showWelcome && agent ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 p-6 text-center">
          <div className="text-4xl">{agent.emoji}</div>
          <div>
            <p className="font-medium">{agent.name}</p>
            <p className="mt-1 text-sm text-muted-foreground">{agent.welcome_msg || "开始对话吧"}</p>
          </div>
          {agent.examples.length > 0 && (
            <div className="flex flex-wrap justify-center gap-2">
              {agent.examples.map((example) => (
                <Button key={example} variant="outline" size="sm" onClick={() => send(example)}>
                  {example}
                </Button>
              ))}
            </div>
          )}
        </div>
      ) : (
        <MessageList
          items={items}
          renderActions={(m) =>
            m.status === "streaming" ? null : (
              <MessageActions
                message={m}
                onRegenerate={regenerate}
                onEdit={editAndResend}
                onRate={rate}
              />
            )
          }
        />
      )}
      {scopedError && <p className="px-4 py-2 text-sm text-red-500">出错：{scopedError}</p>}
      <Composer onSend={send} onStop={stop} generating={ownsActive} />
    </>
  );
}
