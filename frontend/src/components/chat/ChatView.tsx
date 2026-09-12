import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import {
  useCreateSession,
  useMessages,
  useSession,
  type Block,
  type MessageItemData,
} from "@/api/sessions";
import { useAgent, useAgents } from "@/api/agents";
import { apiFetch } from "@/lib/api";
import { streamRequest } from "@/lib/stream";
import { createTokenBuffer } from "@/lib/tokenBuffer";
import type { SSEEvent } from "@/lib/sse";
import type { Citation } from "@/lib/citations";
import Composer, { MAX_ATTACHMENTS, type PendingAttachment } from "@/components/chat/Composer";
import MessageActions from "@/components/chat/MessageActions";
import MessageList from "@/components/chat/MessageList";
import { Button } from "@/components/ui/button";
import { useChatStreamStore, type ToolEvent } from "@/stores/chatStream";

/** tool_result 事件不带工具名，从同一批 tool_call 事件里补上，流式卡片才能显示名称 */
function toolBlock(event: ToolEvent, all: ToolEvent[]): Block {
  if (event.type === "tool_result" && !event.tool) {
    const call = all.find((t) => t.type === "tool_call" && t.id === event.id);
    return { ...event, tool: call?.tool };
  }
  return { ...event };
}

export default function ChatView() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const createSession = useCreateSession();
  const { data: messages = [] } = useMessages(sessionId);
  const { data: session } = useSession(sessionId);
  const { data: agent } = useAgent(session?.agent_id ?? undefined);
  const { data: agents = [] } = useAgents();
  const agentById = new Map(agents.map((a) => [a.id, a]));
  const {
    active,
    error,
    start,
    appendToken,
    appendThinking,
    appendCitation,
    appendToolEvent,
    setError,
    clear,
    clearActive,
  } = useChatStreamStore();
  // 流式 token/thinking 按帧合批提交，避免每 delta 一次 store 更新（高吞吐下会拖垮渲染）
  const [degraded, setDegraded] = useState(false);
  const bufferRef = useRef<ReturnType<typeof createTokenBuffer> | null>(null);
  if (bufferRef.current === null) {
    bufferRef.current = createTokenBuffer((batch) => {
      if (batch.text) appendToken(batch.text, batch.messageId);
      if (batch.thinking) appendThinking(batch.thinking, batch.messageId);
      if (bufferRef.current?.degraded) setDegraded(true);
    });
  }
  // 卸载时取消已排帧，避免回调打到已卸载组件上
  useEffect(() => () => bufferRef.current?.cancel(), []);
  const [openCitation, setOpenCitation] = useState<Citation | null>(null);
  const [attachments, setAttachments] = useState<PendingAttachment[]>([]);
  const attachmentsRef = useRef<PendingAttachment[]>([]);
  useEffect(() => {
    attachmentsRef.current = attachments;
  }, [attachments]);
  // 组件卸载时释放尚未发送的预览 objectURL
  useEffect(
    () => () => {
      attachmentsRef.current.forEach((a) => {
        if (a.previewUrl) URL.revokeObjectURL(a.previewUrl);
      });
    },
    [],
  );
  // ChatView 在会话间复用（无 key）：切换 sessionId 时必须丢弃上一个会话的待发附件，
  // 否则旧会话的 attachment_id 会被发到新会话（后端 404）
  const sessionIdRef = useRef(sessionId);
  const prevSessionRef = useRef(sessionId);
  useEffect(() => {
    sessionIdRef.current = sessionId;
    if (prevSessionRef.current === sessionId) return;
    prevSessionRef.current = sessionId;
    attachmentsRef.current.forEach((a) => {
      if (a.previewUrl) URL.revokeObjectURL(a.previewUrl);
    });
    attachmentsRef.current = [];
    setAttachments([]);
  }, [sessionId]);
  const ownsActive = Boolean(active && active.sessionId === sessionId);
  // 错误只归其产生时的会话：发送创建场景的 error.sessionId 为 null，仅无会话时显示
  const scopedError = error && error.sessionId === (sessionId ?? null) ? error.message : null;

  function onStreamEvent(evt: SSEEvent, targetSession: string) {
    if (evt.event === "message_start") {
      start((evt.data as { message_id: string }).message_id, targetSession);
    } else if (evt.event === "token") {
      const data = evt.data as { delta: string; message_id: string };
      bufferRef.current?.push("text", data.delta, data.message_id);
    } else if (evt.event === "thinking") {
      const data = evt.data as { delta: string; message_id: string };
      bufferRef.current?.push("thinking", data.delta, data.message_id);
    } else if (evt.event === "citation") {
      const data = evt.data as Citation & { message_id: string };
      appendCitation(data, data.message_id);
    } else if (evt.event === "tool_call" || evt.event === "tool_result") {
      const data = evt.data as {
        message_id: string;
        id: string;
        name?: string;
        args?: unknown;
        status?: string;
        elapsed_ms?: number;
        preview?: string;
      };
      const event: ToolEvent =
        evt.event === "tool_call"
          ? { type: "tool_call", id: data.id, tool: data.name, args: data.args }
          : {
              type: "tool_result",
              id: data.id,
              status: data.status,
              elapsed_ms: data.elapsed_ms,
              preview: data.preview,
            };
      appendToolEvent(event, data.message_id);
    } else if (evt.event === "error") {
      setError((evt.data as { message: string }).message, targetSession);
    }
  }

  /** 清掉旧流后请求 SSE，结束后清叠加层并刷新消息/会话列表（send 与 regenerate 共用） */
  async function runStream(path: string, body: unknown, targetSession: string, fallbackError: string) {
    clear();
    setDegraded(false);
    bufferRef.current?.cancel();
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
      // 先提交最后一个不足一帧的批次，再清叠加层，避免丢尾部 token
      bufferRef.current?.flushNow();
      clearActive(streamId);
      await queryClient.invalidateQueries({ queryKey: ["messages", targetSession] });
      await queryClient.invalidateQueries({ queryKey: ["sessions"] });
    }
  }

  async function attach(file: File) {
    // 上限兜底：正常路径由 Composer 拦截并提示
    if (attachmentsRef.current.length >= MAX_ATTACHMENTS) return;
    let target = sessionId;
    if (!target) {
      try {
        const created = await createSession.mutateAsync();
        target = created.id;
        navigate(`/sessions/${created.id}`);
      } catch (err) {
        setError(err instanceof Error ? err.message : "附件上传失败", target ?? null);
        return;
      }
    }
    const form = new FormData();
    form.append("file", file);
    const res = await apiFetch(`/api/v1/sessions/${target}/attachments`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) {
      setError(`附件上传失败（HTTP ${res.status}）`, target);
      return;
    }
    const data = (await res.json()) as { id: string; kind?: string; original_name?: string };
    // 上传期间会话已切换：丢弃结果，避免旧会话的附件进入新会话 chips
    if (sessionIdRef.current !== target) return;
    const isImage = data.kind === "image";
    setAttachments((prev) => [
      ...prev,
      {
        id: data.id,
        name: data.original_name ?? file.name,
        kind: data.kind,
        previewUrl: isImage ? URL.createObjectURL(file) : undefined,
      },
    ]);
  }

  function removeAttachment(id: string) {
    const hit = attachments.find((a) => a.id === id);
    if (hit?.previewUrl) URL.revokeObjectURL(hit.previewUrl);
    setAttachments((prev) => prev.filter((a) => a.id !== id));
  }

  async function send(text: string, mentions: string[] = [], attachmentIds: string[] = []) {
    // 发送即清空 chips 并释放预览 URL；持久化缩略图改走鉴权 blob
    attachments.forEach((a) => {
      if (a.previewUrl) URL.revokeObjectURL(a.previewUrl);
    });
    setAttachments([]);
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
    await runStream(
      `/api/v1/sessions/${target}/messages`,
      { content: text, mentions, attachment_ids: attachmentIds },
      target,
      "发送失败",
    );
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
            ...active.citations.map((c) => ({ type: "citation", ...c })),
            ...active.toolEvents.map((e) => toolBlock(e, active.toolEvents)),
            { type: "text", content: active.content },
          ],
          status: "streaming",
          rating: null,
          error: null,
          created_at: new Date().toISOString(),
        }
      : null;

  const items = streamingMessage ? [...visible, streamingMessage] : visible;
  // 流式叠加层属于当前回合（会话主智能体）；历史消息按 agent_id 映射归属
  const messageAgent = (m: MessageItemData) =>
    m.status === "streaming" ? agent : m.agent_id ? agentById.get(m.agent_id) : undefined;
  const messageIsRelay = (m: MessageItemData) =>
    Boolean(m.agent_id && m.agent_id !== session?.agent_id);
  // 空会话（无消息、无流式叠加）且有智能体时展示欢迎区
  const showWelcome = messages.length === 0 && !streamingMessage && Boolean(agent);

  return (
    <div className="flex min-h-0 flex-1">
      <div className="flex min-w-0 flex-1 flex-col">
        {agent && (
          <div className="flex items-center gap-2 border-b px-4 py-2 text-sm">
            <span>{agent.emoji}</span>
            <span className="font-medium">{agent.name}</span>
            <Link
              to={`/admin/sessions/${sessionId}`}
              className="ml-auto text-xs text-muted-foreground hover:underline"
            >
              查看调用链
            </Link>
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
            agentOf={messageAgent}
            isRelayOf={messageIsRelay}
            onOpenCitation={setOpenCitation}
            degraded={degraded}
            onRetry={regenerate}
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
        <Composer
          onSend={send}
          onStop={stop}
          generating={ownsActive}
          agents={agents}
          attachments={attachments}
          onAttach={attach}
          onRemoveAttachment={removeAttachment}
          sessionKey={sessionId ?? "new"}
        />
      </div>
      {openCitation && (
        <aside
          aria-label="引用依据"
          className="w-80 shrink-0 overflow-y-auto border-l p-4 text-sm"
        >
          <div className="mb-2 flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="truncate font-medium">{openCitation.source}</p>
              <p className="text-xs text-muted-foreground">
                {openCitation.page != null ? `第 ${openCitation.page} 页 · ` : ""}
                相关度 {openCitation.score.toFixed(2)}
              </p>
            </div>
            <Button variant="ghost" size="sm" onClick={() => setOpenCitation(null)}>
              关闭
            </Button>
          </div>
          <p className="whitespace-pre-wrap text-xs leading-relaxed">{openCitation.snippet}</p>
        </aside>
      )}
    </div>
  );
}
