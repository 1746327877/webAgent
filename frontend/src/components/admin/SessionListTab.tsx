import { useMemo, useState } from "react";
import { useAgents } from "@/api/agents";
import { useSessions } from "@/api/sessions";
import TraceView from "@/components/admin/TraceView";

function fmtTime(ts: string | null): string {
  if (!ts) return "-";
  const parsed = new Date(ts);
  return Number.isNaN(parsed.getTime()) ? ts : parsed.toLocaleString("zh-CN", { hour12: false });
}

/** 会话记录：按智能体筛选会话，选中后右侧内嵌该会话的调用链。 */
export default function SessionListTab() {
  const { data, isLoading, error } = useSessions("");
  const { data: agents = [] } = useAgents();
  const [agentFilter, setAgentFilter] = useState("");
  const [pickedId, setPickedId] = useState<string | null>(null);

  const sessions = useMemo(
    () => data?.pages.flatMap((page) => page.items) ?? [],
    [data],
  );
  const agentName = new Map(agents.map((a) => [a.id, a.name]));
  const filtered = useMemo(
    () => (agentFilter ? sessions.filter((s) => s.agent_id === agentFilter) : sessions),
    [sessions, agentFilter],
  );
  // 切换筛选后旧选中可能不在列表内：派生兜底到第一条
  const selectedId = filtered.some((s) => s.id === pickedId)
    ? pickedId
    : (filtered[0]?.id ?? null);

  if (isLoading) return <p className="text-sm text-muted-foreground">加载中…</p>;
  if (error) return <p className="text-sm text-red-500">{error.message}</p>;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <label htmlFor="session-agent-filter" className="text-muted-foreground">
          智能体
        </label>
        <select
          id="session-agent-filter"
          aria-label="按智能体筛选"
          className="h-8 max-w-md rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
          value={agentFilter}
          onChange={(e) => {
            setAgentFilter(e.target.value);
            setPickedId(null);
          }}
        >
          <option value="">全部（{sessions.length}）</option>
          {agents.map((agent) => (
            <option key={agent.id} value={agent.id}>
              {agent.name}
            </option>
          ))}
        </select>
        <span className="text-xs text-muted-foreground">共 {filtered.length} 个会话</span>
      </div>

      {filtered.length === 0 ? (
        <p className="text-sm text-muted-foreground">没有匹配的会话。</p>
      ) : (
        <div className="flex h-[70vh] min-h-0 overflow-hidden rounded-xl border">
          <aside className="w-72 shrink-0 overflow-y-auto border-r p-1">
            {filtered.map((session) => (
              <button
                key={session.id}
                type="button"
                onClick={() => setPickedId(session.id)}
                className={`mb-1 block w-full rounded px-2 py-1.5 text-left text-xs ${
                  session.id === selectedId ? "bg-accent" : "hover:bg-accent/50"
                }`}
              >
                <span className="block truncate">{session.title}</span>
                <span className="block truncate text-muted-foreground">
                  {session.agent_id ? (agentName.get(session.agent_id) ?? "未知智能体") : "无智能体"} ·{" "}
                  {fmtTime(session.last_message_at ?? session.updated_at)}
                  {session.pinned ? " · 置顶" : ""}
                  {session.archived ? " · 已归档" : ""}
                </span>
              </button>
            ))}
          </aside>

          <div className="flex min-w-0 flex-1">
            {selectedId ? (
              <TraceView sessionId={selectedId} />
            ) : (
              <p className="p-4 text-sm text-muted-foreground">选择左侧会话查看调用链。</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
