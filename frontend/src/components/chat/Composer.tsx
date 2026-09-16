import { useEffect, useRef, useState } from "react";
import { ArrowUp, Globe, Paperclip, Square } from "lucide-react";
import AgentAvatar from "@/components/agents/AgentAvatar";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import ModelSelector, { type ModelOption } from "@/components/chat/ModelSelector";
import { cn } from "cn";

interface MentionAgent {
  id: string;
  name: string;
  has_avatar?: boolean;
  updated_at?: string;
}

export interface PendingAttachment {
  id: string;
  /** 图片预览 objectURL；文档无预览 */
  previewUrl?: string;
  /** 原始文件名（chip 展示） */
  name?: string;
  /** image | document；缺省时按 previewUrl 推断 */
  kind?: string;
}

interface Props {
  onSend: (text: string, mentionIds: string[], attachmentIds: string[]) => void;
  onStop: () => void;
  generating: boolean;
  agents?: MentionAgent[];
  attachments?: PendingAttachment[];
  /** 一次可传多个：文件选择器传 1 个，拖放可能一次多个；调用方负责逐个上传与上限兜底 */
  onAttach?: (files: File[]) => void;
  onRemoveAttachment?: (id: string) => void;
  sessionKey?: string;
  /** landing：首页居中大输入框；default：会话内输入框 */
  variant?: "default" | "landing";
  /** 可用模型（来自 GET /api/v1/models） */
  models?: ModelOption[];
  /** 当前显式选择的模型；null 表示智能体默认 */
  modelOverride?: string | null;
  onModelChange?: (model: string | null) => void;
  /** 未选择模型时展示的智能体默认模型名 */
  defaultModelLabel?: string;
  /** 后续消息是否启用联网搜索 */
  webSearch?: boolean;
  onWebSearchChange?: (enabled: boolean) => void;
  /** 后端是否配置了联网搜索 MCP；未配置时按钮禁用 */
  webSearchAvailable?: boolean;
}

const MENTION_TAIL = /@([^\s@]*)$/;
/** 后端 MessageIn.mentions 限制 max_length=2，前端同样封顶，避免必然 422 */
const MAX_MENTIONS = 2;
/** 后端 MessageIn.attachment_ids 限制 max_length=3，前端同样封顶，避免必然 422 */
export const MAX_ATTACHMENTS = 3;
/** 与后端 ALLOWED_EXTS 对齐：图片 + 常见文档 */
export const ATTACH_ACCEPT = ".png,.jpg,.jpeg,.webp,.pdf,.md,.markdown,.txt,.docx";
/** 拖放不受 file input 的 accept 约束，这里按扩展名做一次前端过滤 */
const ACCEPT_EXTS = ATTACH_ACCEPT.split(",").map((s) => s.trim().replace(/^\./, "").toLowerCase());

function isAcceptedFile(file: File): boolean {
  const ext = file.name.slice(file.name.lastIndexOf(".") + 1).toLowerCase();
  return ACCEPT_EXTS.includes(ext);
}

function hasFileDrag(e: React.DragEvent): boolean {
  return Array.from(e.dataTransfer?.types ?? []).includes("Files");
}

export default function Composer({
  onSend,
  onStop,
  generating,
  agents = [],
  attachments = [],
  onAttach,
  onRemoveAttachment,
  sessionKey = "default",
  variant = "default",
  models = [],
  modelOverride = null,
  onModelChange,
  defaultModelLabel = "默认模型",
  webSearch = false,
  onWebSearchChange,
  webSearchAvailable = false,
}: Props) {
  const [input, setInput] = useState("");
  const [mentionQuery, setMentionQuery] = useState<string | null>(null);
  const [mentionIds, setMentionIds] = useState<string[]>([]);
  const [activeIndex, setActiveIndex] = useState(0);
  const [attachHint, setAttachHint] = useState(false);
  const [dropHint, setDropHint] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const dragDepth = useRef(0);
  const fileRef = useRef<HTMLInputElement>(null);

  // 会话切换：ChatView 在会话间复用，必须丢弃上一个会话的草稿与提及（附件由 ChatView 负责）
  const sessionKeyRef = useRef(sessionKey);
  useEffect(() => {
    if (sessionKeyRef.current === sessionKey) return;
    sessionKeyRef.current = sessionKey;
    setInput("");
    setMentionIds([]);
    setMentionQuery(null);
    setAttachHint(false);
    setDropHint(null);
    setDragging(false);
    dragDepth.current = 0;
  }, [sessionKey]);

  const options =
    mentionQuery === null
      ? []
      : agents.filter((a) => a.name.includes(mentionQuery)).slice(0, 5);
  const atCap = mentionIds.length >= MAX_MENTIONS;
  const attachCap = attachments.length >= MAX_ATTACHMENTS;

  function onChange(value: string) {
    setInput(value);
    const match = value.match(MENTION_TAIL);
    setMentionQuery(match ? match[1] : null);
    setActiveIndex(0);
  }

  function select(agent: MentionAgent) {
    // 已满 2 个时拒绝第三个；已选过的仍可补全文本但不重复记 id
    if (atCap && !mentionIds.includes(agent.id)) return;
    setInput((prev) => prev.replace(/@[^\s@]*$/, `@${agent.name}`));
    setMentionIds((prev) => (prev.includes(agent.id) ? prev : [...prev, agent.id]));
    setMentionQuery(null);
    setActiveIndex(0);
  }

  // 用深度计数抵消子元素间移动产生的 dragleave，避免高亮闪烁
  function onDragEnter(e: React.DragEvent) {
    if (!hasFileDrag(e)) return;
    e.preventDefault();
    dragDepth.current += 1;
    setDragging(true);
  }

  function onDragOver(e: React.DragEvent) {
    if (!hasFileDrag(e)) return;
    e.preventDefault(); // 阻止浏览器直接打开文件
    if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
  }

  function onDragLeave(e: React.DragEvent) {
    if (!hasFileDrag(e)) return;
    dragDepth.current = Math.max(0, dragDepth.current - 1);
    if (dragDepth.current === 0) setDragging(false);
  }

  function onDrop(e: React.DragEvent) {
    if (!hasFileDrag(e)) return;
    e.preventDefault();
    dragDepth.current = 0;
    setDragging(false);
    if (attachCap) {
      setAttachHint(true);
      return;
    }
    setAttachHint(false);
    const accepted: File[] = [];
    let rejected = 0;
    for (const file of Array.from(e.dataTransfer?.files ?? [])) {
      if (isAcceptedFile(file)) accepted.push(file);
      else rejected += 1;
    }
    setDropHint(rejected > 0 ? `已忽略 ${rejected} 个不支持的文件` : null);
    // 多余的文件直接丢弃并复用「最多 3 个」提示（与点击上传的上限交互一致）
    const room = MAX_ATTACHMENTS - attachments.length;
    const toUpload = accepted.slice(0, Math.max(0, room));
    if (accepted.length > toUpload.length) setAttachHint(true);
    if (toUpload.length > 0) onAttach?.(toUpload);
  }

  function submit() {
    const text = input.trim();
    if (!text || generating) return;
    // 选过但文本里已删掉的 @ 名字不再提交（例如用户退格删除了提及）
    const validIds = mentionIds
      .filter((id) => {
        const agent = agents.find((a) => a.id === id);
        return agent ? text.includes(agent.name) : false;
      })
      .slice(0, MAX_MENTIONS);
    setInput("");
    setMentionIds([]);
    setMentionQuery(null);
    onSend(text, validIds, attachments.slice(0, MAX_ATTACHMENTS).map((a) => a.id));
  }

  return (
    <div className={cn("flex flex-col gap-2", variant === "default" && "border-t p-3")}>
      {attachments.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {attachments.map((attachment) => {
            const isImage = attachment.kind
              ? attachment.kind === "image"
              : Boolean(attachment.previewUrl);
            return (
              <div
                key={attachment.id}
                className="relative flex items-center gap-2 rounded-md border bg-muted/40 py-1 pr-6 pl-1"
              >
                {isImage && attachment.previewUrl ? (
                  <img
                    src={attachment.previewUrl}
                    alt="图片预览"
                    className="h-12 w-12 rounded object-cover"
                  />
                ) : (
                  <span
                    aria-hidden
                    className="flex h-12 w-12 items-center justify-center text-lg"
                  >
                    📄
                  </span>
                )}
                {attachment.name && (
                  <span className="max-w-40 truncate text-xs">{attachment.name}</span>
                )}
                <button
                  type="button"
                  aria-label="移除附件"
                  className="absolute -top-1.5 -right-1.5 flex h-4 w-4 items-center justify-center rounded-full bg-foreground text-[10px] leading-none text-background"
                  onClick={() => onRemoveAttachment?.(attachment.id)}
                >
                  ×
                </button>
              </div>
            );
          })}
        </div>
      )}
      {attachHint && (
        <p className="text-xs text-muted-foreground">最多上传 {MAX_ATTACHMENTS} 个附件</p>
      )}
      {dropHint && <p className="text-xs text-muted-foreground">{dropHint}</p>}
      <div
        data-testid="composer-dropzone"
        className={cn(
          "relative flex flex-col gap-2 rounded-xl border bg-background p-2 shadow-sm focus-within:border-ring",
          dragging && "border-ring ring-2 ring-ring/40",
        )}
        onDragEnter={onDragEnter}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
      >
        <input
          ref={fileRef}
          type="file"
          accept={ATTACH_ACCEPT}
          data-testid="attachment-input"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = ""; // 允许连续选择同一文件
            if (!file) return;
            // 已满 3 个时拒绝第 4 个并提示（与 mention 上限的交互一致）
            if (attachCap) {
              setAttachHint(true);
              return;
            }
            setAttachHint(false);
            onAttach?.([file]);
          }}
        />
        {mentionQuery !== null && options.length > 0 && (
          <div className="absolute bottom-full left-0 z-10 mb-2 w-56">
            {atCap && (
              <p className="mb-1 rounded-md bg-muted px-2 py-1 text-xs text-muted-foreground">
                最多同时 @ 2 个智能体
              </p>
            )}
            <Card size="sm" role="listbox" aria-label="提及智能体" className="gap-0.5 p-1">
              {options.map((a, i) => (
                <Button
                  key={a.id}
                  type="button"
                  variant="ghost"
                  size="sm"
                  role="option"
                  aria-selected={i === activeIndex}
                  className={cn(
                    "w-full justify-start font-normal",
                    i === activeIndex && "bg-muted",
                  )}
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => select(a)}
                >
                  <AgentAvatar
                    agentId={a.id}
                    name={a.name}
                    hasAvatar={a.has_avatar}
                    version={a.updated_at}
                    className="size-4 text-[9px]"
                  />
                  <span>{a.name}</span>
                </Button>
              ))}
            </Card>
          </div>
        )}
        <Textarea
          value={input}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (mentionQuery !== null && options.length > 0) {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setActiveIndex((i) => (i + 1) % options.length);
                return;
              }
              if (e.key === "ArrowUp") {
                e.preventDefault();
                setActiveIndex((i) => (i - 1 + options.length) % options.length);
                return;
              }
              if (e.key === "Enter") {
                e.preventDefault();
                select(options[Math.min(activeIndex, options.length - 1)]);
                return;
              }
            }
            if (e.key === "Escape") {
              setMentionQuery(null);
              return;
            }
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder="输入问题，Enter 发送"
          className={cn(
            "min-h-24 resize-none border-0 bg-transparent px-3 py-3 text-base shadow-none focus-visible:ring-0 md:text-base",
            variant === "landing" && "min-h-40 md:text-base",
          )}
        />
        <div className="flex items-center gap-2 px-1">
          <ModelSelector
            models={models}
            value={modelOverride}
            defaultLabel={defaultModelLabel}
            onChange={(model) => onModelChange?.(model)}
          />
          <Button
            type="button"
            variant={webSearch ? "default" : "outline"}
            size="icon"
            aria-label="联网搜索"
            aria-pressed={webSearch}
            title={webSearchAvailable ? "联网搜索（对随后发送的消息生效）" : "联网搜索未配置"}
            disabled={!webSearchAvailable}
            onClick={() => onWebSearchChange?.(!webSearch)}
          >
            <Globe />
          </Button>
          <Button
            type="button"
            variant="outline"
            size="icon"
            aria-label="上传附件"
            title="上传附件"
            onClick={() => {
              if (attachCap) {
                setAttachHint(true);
                return;
              }
              fileRef.current?.click();
            }}
          >
            <Paperclip />
          </Button>
          <span className="hidden text-xs text-muted-foreground sm:inline">
            @ 提及智能体 · Shift+Enter 换行
          </span>
          <div className="ml-auto flex gap-2">
            {generating ? (
              <Button variant="secondary" size="icon" aria-label="停止" title="停止" onClick={onStop}>
                <Square />
              </Button>
            ) : (
              <Button size="icon" aria-label="发送" title="发送" onClick={submit}>
                <ArrowUp />
              </Button>
            )}
          </div>
        </div>
        {dragging && (
          <div className="pointer-events-none absolute inset-0 z-20 flex items-center justify-center rounded-xl border-2 border-dashed border-ring bg-background/80 text-sm font-medium text-muted-foreground">
            松开即可上传附件
          </div>
        )}
      </div>
    </div>
  );
}
