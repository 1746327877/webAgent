import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMessages, type MessageItemData } from "@/api/sessions";
import {
  downloadSpansCsv,
  useSpanLogs,
  useTrace,
  type SpanItem,
} from "@/api/admin";
import JsonTree from "@/components/admin/JsonTree";
import { Button } from "@/components/ui/button";

const SPAN_COLORS: Record<string, string> = {
  llm: "#6366f1",
  tool: "#10b981",
  retrieval: "#f59e0b",
  model_switch: "#ef4444",
};
const FALLBACK_COLOR = "#94a3b8";
const TYPE_OPTIONS = ["llm", "tool", "retrieval", "model_switch"];
const STATUS_OPTIONS = ["ok", "error", "stopped"];

function messagePreview(message: MessageItemData): string {
  const text = message.blocks.find((block) => block.type === "text")?.content;
  return text?.trim() || "（无文本）";
}

function fmtTime(ts: string): string {
  const parsed = new Date(ts);
  return Number.isNaN(parsed.getTime()) ? ts : parsed.toLocaleString("zh-CN", { hour12: false });
}

interface Bar {
  span: SpanItem;
  left: number;
  width: number;
  depth: number;
}

/** 布局计算：以 trace 起点为 0 归一化；父 span 缺失/成环时按顶层处理，避免死循环 */
function layoutBars(spans: SpanItem[]): Bar[] {
  if (spans.length === 0) return [];
  const parsed = spans.map((span) => {
    const rawStart = Date.parse(span.started_at);
    const validStart = Number.isFinite(rawStart);
    const start = validStart ? rawStart : 0;
    const rawEnd = span.ended_at ? Date.parse(span.ended_at) : NaN;
    const fallbackEnd = start + Math.max(span.duration_ms ?? 0, 0);
    const end = Number.isFinite(rawEnd) ? Math.max(rawEnd, start) : fallbackEnd;
    return { span, start, end, validStart };
  });
  // 时间戳非法的 span 不参与 t0/t1 计算，只按 0 偏移兜底渲染，避免拉歪整条时间轴
  const valid = parsed.filter((p) => p.validStart);
  const t0 = valid.length > 0 ? Math.min(...valid.map((p) => p.start)) : 0;
  const t1 = Math.max(...valid.map((p) => p.end), t0);
  const total = t1 - t0 || 1;
  const byId = new Map(parsed.map((p) => [p.span.id, p.span]));
  const depthOf = (span: SpanItem): number => {
    let depth = 0;
    let cursor = span.parent_span_id;
    const seen = new Set<string>([span.id]);
    while (cursor && byId.has(cursor) && !seen.has(cursor) && depth < 20) {
      seen.add(cursor);
      depth += 1;
      cursor = byId.get(cursor)!.parent_span_id;
    }
    return depth;
  };
  return parsed.map(({ span, start, end }) => {
    const left = Math.min(Math.max((start - t0) / total, 0), 0.99) * 100;
    // 最小可见宽度 0.5%，且不越出轨道右缘（零时长 span 仍可见、可点）
    const width = Math.max(Math.min(((end - start) / total) * 100, 100 - left), 0.5);
    return { span, left, width, depth: depthOf(span) };
  });
}

function Waterfall({ spans, onSelect }: { spans: SpanItem[]; onSelect: (span: SpanItem) => void }) {
  const bars = useMemo(() => layoutBars(spans), [spans]);
  if (spans.length === 0) {
    return <p className="p-3 text-sm text-muted-foreground">该消息暂无 span 数据</p>;
  }
  return (
    <div className="space-y-1.5 p-3">
      {bars.map(({ span, left, width, depth }) => (
        <div key={span.id} className="flex items-center gap-2">
          <span
            className="w-40 shrink-0 truncate text-xs"
            style={{ paddingLeft: depth * 12 }}
            title={span.name ?? span.type}
          >
            {`${span.name ?? span.type} · ${span.type}`}
          </span>
          <div className="relative h-4 min-w-0 flex-1 rounded bg-muted/60">
            <button
              type="button"
              aria-label={`span-${span.type}`}
              title={`${span.name ?? span.type} ${Math.round(span.duration_ms ?? 0)}ms`}
              className="absolute inset-y-0 block h-4 rounded hover:opacity-80"
              style={{
                left: `${left}%`,
                width: `${width}%`,
                background: SPAN_COLORS[span.type] ?? FALLBACK_COLOR,
              }}
              onClick={() => onSelect(span)}
            />
          </div>
          <span className="w-14 shrink-0 text-right text-xs tabular-nums text-muted-foreground">
            {Math.round(span.duration_ms ?? 0)}ms
          </span>
        </div>
      ))}
    </div>
  );
}

function SpanDrawer({ span, onClose }: { span: SpanItem; onClose: () => void }) {
  return (
    <aside aria-label="span 详情" className="w-96 shrink-0 overflow-y-auto border-l p-4 text-sm">
      <div className="mb-3 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate font-medium">{span.name ?? span.type}</p>
          <p className="text-xs text-muted-foreground">
            {span.type} · {span.status}
          </p>
        </div>
        <Button variant="ghost" size="sm" onClick={onClose}>
          关闭
        </Button>
      </div>
      <dl className="mb-3 grid grid-cols-2 gap-x-2 gap-y-1 text-xs">
        <dt className="text-muted-foreground">耗时</dt>
        <dd className="tabular-nums">{span.duration_ms ?? "-"} ms</dd>
        <dt className="text-muted-foreground">Prompt Token</dt>
        <dd className="tabular-nums">{span.prompt_tokens ?? "-"}</dd>
        <dt className="text-muted-foreground">Completion Token</dt>
        <dd className="tabular-nums">{span.completion_tokens ?? "-"}</dd>
        <dt className="text-muted-foreground">模型</dt>
        <dd>{span.model ?? "-"}</dd>
      </dl>
      {span.error && <p className="mb-3 break-all text-xs text-red-500">{span.error}</p>}
      <div className="space-y-2">
        <JsonTree data={span.input} name="输入" />
        <JsonTree data={span.output} name="输出" />
      </div>
    </aside>
  );
}

export default function AdminTracePage() {
  const { sessionId } = useParams();
  const { data: messages, isLoading: messagesLoading } = useMessages(sessionId);
  const assistantMessages = useMemo(
    () => (messages ?? []).filter((message) => message.role === "assistant"),
    [messages],
  );
  // 显式选择优先；选中消息不在当前会话（切换会话/刷新）时自动回落最后一条
  const [pickedId, setPickedId] = useState<string | null>(null);
  const selectedMessageId =
    pickedId && assistantMessages.some((message) => message.id === pickedId)
      ? pickedId
      : assistantMessages.at(-1)?.id;

  const { data: trace, isLoading: traceLoading, error: traceError } = useTrace(selectedMessageId);
  const [type, setType] = useState("");
  const [status, setStatus] = useState("");
  const [drawer, setDrawer] = useState<{ viewKey: string; span: SpanItem } | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);

  // 列表与 CSV 导出共用同一份筛选参数；列表额外请求后端单页上限，
  // 导出则由后端流式输出全部命中数据
  const filters = { session_id: sessionId, type: type || undefined, status: status || undefined };
  const listFilters = { ...filters, limit: 200 };
  const { data: logs } = useSpanLogs(listFilters);

  // 抽屉绑定当前会话+消息：切换会话/消息后旧 span 不再展示，无需额外副作用清理
  const viewKey = `${sessionId ?? ""}:${selectedMessageId ?? ""}`;
  const selectedSpan = drawer?.viewKey === viewKey ? drawer.span : null;

  async function onExport() {
    setExportError(null);
    try {
      await downloadSpansCsv(filters);
    } catch (err) {
      setExportError(err instanceof Error ? err.message : "导出失败");
    }
  }

  return (
    <div className="flex min-h-0 flex-1">
      <aside className="w-56 shrink-0 overflow-y-auto border-r p-2">
        <p className="px-2 py-1 text-xs text-muted-foreground">助手消息</p>
        {assistantMessages.length === 0 && !messagesLoading && (
          <p className="px-2 text-xs text-muted-foreground">暂无消息</p>
        )}
        {assistantMessages.map((message, index) => (
          <button
            key={message.id}
            type="button"
            onClick={() => setPickedId(message.id)}
            className={`mb-1 block w-full truncate rounded px-2 py-1.5 text-left text-xs ${
              message.id === selectedMessageId ? "bg-accent" : "hover:bg-accent/50"
            }`}
          >
            {index + 1}. {messagePreview(message)}
          </button>
        ))}
      </aside>

      <div className="flex min-w-0 flex-1 flex-col overflow-y-auto">
        <div className="flex items-center justify-between gap-2 border-b px-4 py-2">
          <div className="min-w-0">
            <h1 className="text-sm font-semibold">🔍 会话调用链</h1>
            <p className="truncate text-xs text-muted-foreground">会话 {sessionId ?? "-"}</p>
          </div>
          <Link to="/admin" className="shrink-0 text-xs text-muted-foreground hover:underline">
            ← 返回仪表盘
          </Link>
        </div>

        {traceLoading && <p className="p-4 text-sm text-muted-foreground">加载中…</p>}
        {traceError && <p className="p-4 text-sm text-red-500">{traceError.message}</p>}
        {!traceLoading && !traceError && !trace && (
          <p className="p-4 text-sm text-muted-foreground">选择一条助手消息查看调用链</p>
        )}

        {trace && (
          <>
            <section className="border-b">
              <div className="flex items-center justify-between px-3 pt-3">
                <span className="text-sm font-medium">Waterfall</span>
                <span className="text-xs text-muted-foreground">{trace.spans.length} 个 span</span>
              </div>
              <Waterfall spans={trace.spans} onSelect={(span) => setDrawer({ viewKey, span })} />
            </section>

            <section className="p-3">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium">工具日志</span>
                <select
                  aria-label="类型筛选"
                  className="rounded border bg-transparent px-1 py-0.5 text-xs"
                  value={type}
                  onChange={(e) => setType(e.target.value)}
                >
                  <option value="">全部</option>
                  {TYPE_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
                <select
                  aria-label="状态筛选"
                  className="rounded border bg-transparent px-1 py-0.5 text-xs"
                  value={status}
                  onChange={(e) => setStatus(e.target.value)}
                >
                  <option value="">全部</option>
                  {STATUS_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
                <Button size="sm" variant="outline" onClick={onExport}>
                  导出 CSV
                </Button>
                {exportError && <span className="text-xs text-red-500">{exportError}</span>}
              </div>
              {logs && logs.total > logs.items.length && (
                <p className="mb-2 text-xs text-muted-foreground">
                  {`共 ${logs.total} 条，显示前 ${logs.items.length} 条`}
                </p>
              )}
              <table className="w-full text-left text-xs">
                <thead className="text-muted-foreground">
                  <tr className="border-b">
                    <th className="px-2 py-1.5 font-medium">时间</th>
                    <th className="px-2 py-1.5 font-medium">类型</th>
                    <th className="px-2 py-1.5 font-medium">名称</th>
                    <th className="px-2 py-1.5 font-medium">状态</th>
                    <th className="px-2 py-1.5 font-medium">耗时</th>
                    <th className="px-2 py-1.5 font-medium">模型</th>
                    <th className="px-2 py-1.5 font-medium">Token</th>
                  </tr>
                </thead>
                <tbody>
                  {(logs?.items ?? []).map((span) => (
                    <tr key={span.id} className="border-b last:border-0">
                      <td className="px-2 py-1.5 tabular-nums">{fmtTime(span.started_at)}</td>
                      <td className="px-2 py-1.5">{span.type}</td>
                      <td className="px-2 py-1.5">{span.name ?? "-"}</td>
                      <td className="px-2 py-1.5">{span.status}</td>
                      <td className="px-2 py-1.5 tabular-nums">{span.duration_ms ?? "-"} ms</td>
                      <td className="px-2 py-1.5">{span.model ?? "-"}</td>
                      <td className="px-2 py-1.5 tabular-nums">
                        {span.prompt_tokens ?? 0} / {span.completion_tokens ?? 0}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {logs && logs.total === 0 && (
                <p className="py-6 text-center text-xs text-muted-foreground">暂无日志</p>
              )}
            </section>
          </>
        )}
      </div>

      {selectedSpan && <SpanDrawer span={selectedSpan} onClose={() => setDrawer(null)} />}
    </div>
  );
}
