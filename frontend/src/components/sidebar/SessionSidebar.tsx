import { useState } from "react";
import { NavLink, useMatch, useNavigate } from "react-router-dom";
import {
  useCreateSession,
  useDeleteSession,
  useSessions,
  useUpdateSession,
  type SessionItem,
} from "@/api/sessions";
import { groupByDate } from "@/lib/time";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";

export default function SessionSidebar() {
  const [query, setQuery] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  const debounced = useDebouncedValue(query, 300);
  const { data, fetchNextPage, hasNextPage } = useSessions(debounced, showArchived);
  const createSession = useCreateSession();
  const updateSession = useUpdateSession();
  const deleteSession = useDeleteSession();
  const navigate = useNavigate();
  // 用 location 匹配而非 useParams：sidebar 渲染在父路由元素中（Outlet 之外），
  // 显式匹配当前 URL 才能稳定拿到正在浏览的会话 id（不依赖路由嵌套层级）
  const match = useMatch("/sessions/:sessionId");
  const activeId = match?.params.sessionId;

  const items = data?.pages.flatMap((p) => p.items) ?? [];
  // 后端按 pinned desc 返回：置顶项单独成组（保持接口顺序），其余再做日期分组
  const pinnedItems = items.filter((s) => s.pinned);
  const groups = groupByDate(items.filter((s) => !s.pinned));

  async function onNew() {
    const s = await createSession.mutateAsync();
    navigate(`/sessions/${s.id}`);
  }

  function onRename(id: string, title: string) {
    const next = window.prompt("重命名会话", title);
    if (next && next.trim()) updateSession.mutate({ id, patch: { title: next.trim() } });
  }

  function onDelete(id: string) {
    if (window.confirm("删除该会话？")) {
      deleteSession.mutate(id);
      if (activeId === id) navigate("/");
    }
  }

  function renderItem(s: SessionItem) {
    return (
      <div key={s.id} className="group flex items-center">
        <NavLink
          to={`/sessions/${s.id}`}
          className={({ isActive }) =>
            `min-w-0 flex-1 truncate rounded px-2 py-1.5 text-sm ${isActive ? "bg-accent" : "hover:bg-accent/50"}`
          }
        >
          {s.pinned ? "📌 " : ""}{s.title}
        </NavLink>
        <button className="hidden px-1 text-xs text-muted-foreground group-hover:block"
                onClick={() => onRename(s.id, s.title)}>改</button>
        {!showArchived && (
          <button className="hidden px-1 text-xs text-muted-foreground group-hover:block"
                  onClick={() => updateSession.mutate({ id: s.id, patch: { pinned: !s.pinned } })}>{s.pinned ? "取消" : "置顶"}</button>
        )}
        {showArchived ? (
          <button className="hidden px-1 text-xs text-muted-foreground group-hover:block"
                  onClick={() => updateSession.mutate({ id: s.id, patch: { archived: false } })}>恢复</button>
        ) : (
          <button className="hidden px-1 text-xs text-muted-foreground group-hover:block"
                  onClick={() => updateSession.mutate({ id: s.id, patch: { archived: true } })}>归档</button>
        )}
        <button className="hidden px-1 text-xs text-red-500 group-hover:block"
                onClick={() => onDelete(s.id)}>删</button>
      </div>
    );
  }

  return (
    <aside className="flex w-72 shrink-0 flex-col border-r">
      <div className="space-y-2 p-3">
        <Button className="w-full" onClick={onNew}>＋ 新建任务</Button>
        <Input placeholder="搜索会话…" maxLength={64} value={query} onChange={(e) => setQuery(e.target.value)} />
      </div>
      <nav className="flex-1 overflow-y-auto px-2 pb-3">
        {pinnedItems.length > 0 && (
          <div>
            <p className="px-2 pt-3 pb-1 text-xs text-muted-foreground">置顶</p>
            {pinnedItems.map(renderItem)}
          </div>
        )}
        {groups.map((g) => (
          <div key={g.label}>
            <p className="px-2 pt-3 pb-1 text-xs text-muted-foreground">{g.label}</p>
            {g.items.map(renderItem)}
          </div>
        ))}
        {hasNextPage && (
          <Button variant="ghost" size="sm" className="mt-2 w-full" onClick={() => fetchNextPage()}>
            加载更多
          </Button>
        )}
      </nav>
      <div className="space-y-1 border-t p-2">
        <NavLink
          to="/agents"
          className={({ isActive }) =>
            `block rounded px-2 py-1.5 text-sm ${isActive ? "bg-accent" : "hover:bg-accent/50"}`
          }
        >
          🤖 智能体
        </NavLink>
        <Button variant="ghost" size="sm" className="w-full" onClick={() => setShowArchived((v) => !v)}>
          {showArchived ? "返回" : "查看归档"}
        </Button>
      </div>
    </aside>
  );
}
