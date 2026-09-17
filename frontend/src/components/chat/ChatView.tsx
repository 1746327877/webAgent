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
import { useAgent, useAgents, useModels, toAgentBadge } from "@/api/agents";
import { useWebSearchStatus } from "@/api/capabilities";
import AgentAvatar from "@/components/agents/AgentAvatar";
import { apiFetch } from "@/lib/api";
import { streamRequest } from "@/lib/stream";
import { createTokenBuffer } from "@/lib/tokenBuffer";
import type { SSEEvent } from "@/lib/sse";
import type { Citation } from "@/lib/citations";
import Composer, { MAX_ATTACHMENTS, type PendingAttachment } from "@/components/chat/Composer";
import ArtifactPanel from "@/components/chat/ArtifactPanel";
import { useExportMarkdown } from "@/api/artifacts";
import MessageActions from "@/components/chat/MessageActions";
import MessageList from "@/components/chat/MessageList";
import { Button } from "@/components/ui/button";
import { useChatStreamStore, type ToolEvent } from "@/stores/chatStream";
import { useComposerStore } from "@/stores/composer";

/** tool_result 事件不带工具名，从同一批 tool_call 事件里补上，流式卡片才能显示名称 */
function toolBlock(event: ToolEvent, all: ToolEvent[]): Block {
  if (event.type === "tool_result" && !event.tool) {
    const call = all.find((t) => t.type === "tool_call" && t.id === event.id);
    return { ...event, tool: call?.tool };
  }
  return { ...event };
}

/** 用户消息纯文本，用于乐观消息与回填后真实消息的等值判断。 */
function messageText(message: MessageItemData): string {
  return message.blocks
    .filter((block) => block.type === "text")
    .map((block) => block.content ?? "")
    .join("\n");
}

/** 发送瞬间本地构造的用户消息：真实消息回填前先展示，避免"等模型答完才看到自己说的话"。 */
function optimisticUserMessage(
  text: string,
  attachments: MessageItemData["attachments"] = [],
): MessageItemData {
  return {
    id: `pending-${Date.now()}`,
    role: "user",
    blocks: [{ type: "text", content: text }],
    status: "done",
    rating: null,
    error: null,
    created_at: new Date().toISOString(),
    // 带上附件才能在发送瞬间就显示文件名 chip（否则要等流结束重拉消息才出现）
    attachments,
  };
}

export default function ChatView() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const createSession = useCreateSession();
  const { data: messages = [], isLoading: messagesLoading } = useMessages(sessionId);
  const { data: session } = useSession(sessionId);
  const { data: agent } = useAgent(session?.agent_id ?? undefined);
  const { data: agents = [] } = useAgents();
  const { data: models = [] } = useModels();
  const modelOverride = useComposerStore((s) => s.modelOverride);
  const setModelOverride = useComposerStore((s) => s.setModelOverride);
  const webSearch = useComposerStore((s) => s.webSearch);
  const setWebSearch = useComposerStore((s) => s.setWebSearch);
  const thinking = useComposerStore((s) => s.thinking);
  const setThinking = useComposerStore((s) => s.setThinking);
  // 会话产物（导出纪要等）：面板开关 + 导出动作
  const [artifactsOpen, setArtifactsOpen] = useState(false);
  const exportMarkdown = useExportMarkdown(sessionId);
  // 未配置/不可用时按钮禁用；轮询通过 useWebSearchStatus 内置的 refetchInterval
  const { data: webSearchStatus } = useWebSearchStatus();
  const webSearchAvailable = Boolean(webSearchStatus?.enabled && webSearchStatus?.healthy);
  const defaultModel = (a?: { model_config?: Record<string, unknown> }) => {
    const m = a?.model_config?.model;
    return typeof m === "string" && m ? m : null;
  };
  const defaultModelLabel = defaultModel(agent) ?? defaultModel(agents[0]) ?? "默认模型";
  // 深度思考是否可用，取决于"当前实际使用的模型"是否具备 thinking 能力
  // （Ollama 对不支持的模型会拒绝 think 参数，因此不支持时前端置灰、且不上报该字段）
  const currentModelName =
    modelOverride ?? defaultModel(agent) ?? defaultModel(agents[0]) ?? "";
  const thinkingAvailable = Boolean(
    currentModelName &&
      models.find((m) => m.name === currentModelName)?.capabilities?.includes("thinking"),
  );
  const agentById = new Map(agents.map((a) => [a.id, a]));
  // 提及下拉/消息徽标只需要头像与名字，避免整份 AgentItem 透传
  const agentBadges = agents.map(toAgentBadge);
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
  // 乐观用户消息：发送后立即显示；流结束（runStream finally）清掉，避免残留
  const [pendingUser, setPendingUser] = useState<{
    session: string;
    message: MessageItemData;
  } | null>(null);
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
        links?: string[];
        images?: string[];
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
              links: data.links,
              images: data.images,
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
      setPendingUser(null);
      await queryClient.invalidateQueries({ queryKey: ["messages", targetSession] });
      // doc_convert 等工具在流中途产出新产物，结束时刷新让产物区出现新条目
      await queryClient.invalidateQueries({ queryKey: ["artifacts", targetSession] });
      await queryClient.invalidateQueries({ queryKey: ["sessions"] });
    }
  }

  async function attach(files: File[]) {
    // 上限兜底：正常路径由 Composer 拦截并提示；这里按剩余额度截断，避免并发拖放超发
    const room = MAX_ATTACHMENTS - attachmentsRef.current.length;
    const accepted = files.slice(0, Math.max(0, room));
    if (accepted.length === 0) return;
    let target = sessionId;
    if (!target) {
      // 落地态一次可能拖入多个：只创建一次会话，再逐个上传
      try {
        const created = await createSession.mutateAsync();
        target = created.id;
        navigate(`/sessions/${created.id}`);
      } catch (err) {
        setError(err instanceof Error ? err.message : "附件上传失败", target ?? null);
        return;
      }
      // 新建即当前会话：先行同步 ref，避免首个上传返回时 navigate 尚未生效而误判为已切会话
      sessionIdRef.current = target;
    }
    for (const file of accepted) {
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
    setPendingUser({
      session: target,
      message: optimisticUserMessage(
        text,
        attachments.map((a) => ({ id: a.id, original_name: a.name ?? "附件", kind: a.kind })),
      ),
    });
    await runStream(
      `/api/v1/sessions/${target}/messages`,
      {
        content: text,
        mentions,
        attachment_ids: attachmentIds,
        // 仅在用户显式选过模型时上报，保持默认行为与既有请求体一致
        ...(modelOverride ? { model_override: modelOverride } : {}),
        // 联网搜索为对话级开关：仅在开启时上报
        ...(webSearch ? { web_search: true } : {}),
        // 深度思考：只有模型支持时才上报（false 也要报，才能真正关掉默认开启的思考）
        ...(thinkingAvailable ? { thinking } : {}),
      },
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

  /** 导出当前会话为 Markdown 产物；成功后自动打开产物区，让用户立刻看到结果 */
  async function exportMinutes() {
    if (!sessionId) return;
    try {
      await exportMarkdown.mutateAsync();
      setArtifactsOpen(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "导出失败", sessionId);
    }
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
    // 首页居中落地态：无会话时展示欢迎信息 + 大输入框，发送即创建会话
    const landingAgent = agent ?? agents[0];
    return (
      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
        <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col items-center justify-center gap-6 px-4 py-10">
          <div className="text-center">
            {landingAgent ? (
              <AgentAvatar
                agentId={landingAgent.id}
                name={landingAgent.name}
                hasAvatar={landingAgent.has_avatar}
                version={landingAgent.updated_at}
                className="mx-auto size-16 text-2xl"
              />
            ) : (
              <div className="text-5xl">💬</div>
            )}
            <h1 className="mt-3 text-2xl font-semibold tracking-tight">
              {landingAgent ? landingAgent.name : "开始新的对话"}
            </h1>
            <p className="mt-2 text-sm text-muted-foreground">
              {landingAgent?.welcome_msg || "输入你的问题，或 @ 提及智能体协作"}
            </p>
          </div>
          <div className="w-full">
            <Composer
              onSend={send}
              onStop={stop}
              generating={ownsActive}
              agents={agentBadges}
              attachments={attachments}
              onAttach={attach}
              onRemoveAttachment={removeAttachment}
              sessionKey={sessionId ?? "new"}
              variant="landing"
              models={models}
              modelOverride={modelOverride}
              onModelChange={setModelOverride}
              defaultModelLabel={defaultModelLabel}
              webSearch={webSearch}
              onWebSearchChange={setWebSearch}
              webSearchAvailable={webSearchAvailable}
              thinking={thinking}
              onThinkingChange={setThinking}
              thinkingAvailable={thinkingAvailable}
            />
          </div>
          <p className="text-xs text-muted-foreground">
            <kbd className="rounded border px-1">@</kbd> 提及智能体 ·{" "}
            <kbd className="rounded border px-1">/</kbd> 命令 · Enter 发送
          </p>
          {landingAgent && landingAgent.examples.length > 0 && (
            <div className="flex flex-wrap justify-center gap-2">
              {landingAgent.examples.map((example) => (
                <Button key={example} variant="outline" size="sm" onClick={() => send(example)}>
                  {example}
                </Button>
              ))}
            </div>
          )}
          {scopedError && <p className="text-sm text-red-500">出错：{scopedError}</p>}
        </div>
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

  // 乐观用户消息：仅当属于当前会话、且最后一条真实消息还不是它时显示（避免与回填后的真实消息重复）
  const pendingVisible =
    pendingUser && pendingUser.session === sessionId ? pendingUser.message : null;
  const lastVisibleMessage = visible[visible.length - 1];
  const showPending =
    pendingVisible !== null &&
    !(
      lastVisibleMessage?.role === "user" &&
      messageText(lastVisibleMessage) === messageText(pendingVisible)
    );

  const items = [
    ...visible,
    ...(showPending && pendingVisible ? [pendingVisible] : []),
    ...(streamingMessage ? [streamingMessage] : []),
  ];
  // 流式叠加层属于当前回合（会话主智能体）；历史消息按 agent_id 映射归属
  const messageAgent = (m: MessageItemData) => {
    const owner = m.status === "streaming" ? agent : m.agent_id ? agentById.get(m.agent_id) : undefined;
    return owner ? toAgentBadge(owner) : undefined;
  };
  const messageIsRelay = (m: MessageItemData) =>
    Boolean(m.agent_id && m.agent_id !== session?.agent_id);
  // 空会话（无消息、无流式叠加、无乐观消息）且有智能体时展示欢迎区
  const showWelcome =
    messages.length === 0 && !streamingMessage && !showPending && Boolean(agent);

  return (
    <div className="flex min-h-0 flex-1">
      <div className="flex min-w-0 flex-1 flex-col">
        {(agent || session) && (
          <div className="flex items-center gap-2 border-b px-4 py-2 text-sm">
            <span className="min-w-0 flex-1 truncate font-medium" title={session?.title}>
              {session?.title || "新对话"}
            </span>
            {agent && (
              <span className="flex shrink-0 items-center gap-1 text-xs text-muted-foreground">
                <AgentAvatar
                  agentId={agent.id}
                  name={agent.name}
                  hasAvatar={agent.has_avatar}
                  version={agent.updated_at}
                  className="size-4 text-[9px]"
                />
                <span>{agent.name}</span>
              </span>
            )}
            <Link
              to={`/admin/sessions/${sessionId}`}
              className="shrink-0 text-xs text-muted-foreground hover:underline"
            >
              查看调用链
            </Link>
            {sessionId && (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={exportMarkdown.isPending}
                  onClick={() => void exportMinutes()}
                >
                  {exportMarkdown.isPending ? "导出中…" : "导出纪要"}
                </Button>
                <Button variant="outline" size="sm" onClick={() => setArtifactsOpen((open) => !open)}>
                  产物
                </Button>
              </>
            )}
          </div>
        )}
        {showWelcome && agent ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 p-6 text-center">
            <AgentAvatar
              agentId={agent.id}
              name={agent.name}
              hasAvatar={agent.has_avatar}
              version={agent.updated_at}
              className="size-14 text-xl"
            />
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
        ) : messagesLoading && !streamingMessage && !showPending ? (
          // 等历史消息加载完再挂载列表：否则会先渲染顶部、再跳到底部，观感割裂
          <p className="flex-1 p-4 text-sm text-muted-foreground">加载中…</p>
        ) : (
          <MessageList
            items={items}
            sessionKey={sessionId ?? "new"}
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
          agents={agentBadges}
          attachments={attachments}
          onAttach={attach}
          onRemoveAttachment={removeAttachment}
          sessionKey={sessionId ?? "new"}
          models={models}
          modelOverride={modelOverride}
          onModelChange={setModelOverride}
          defaultModelLabel={defaultModelLabel}
          webSearch={webSearch}
          onWebSearchChange={setWebSearch}
          webSearchAvailable={webSearchAvailable}
          thinking={thinking}
          onThinkingChange={setThinking}
          thinkingAvailable={thinkingAvailable}
        />
      </div>
      {sessionId && artifactsOpen && (
        <ArtifactPanel sessionId={sessionId} onClose={() => setArtifactsOpen(false)} />
      )}
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
              {openCitation.headings?.length ? (
                <p className="truncate text-xs text-muted-foreground">
                  {openCitation.headings.join(" › ")}
                </p>
              ) : null}
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
