import { useState } from "react";
import { NavLink, useNavigate, useParams } from "react-router-dom";
import {
  useCreateSession,
  useDeleteSession,
  useSessions,
  useUpdateSession,
} from "@/api/sessions";
import { groupByDate } from "@/lib/time";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";

export default function SessionSidebar() {
  const [query, setQuery] = useState("");
  const debounced = useDebouncedValue(query, 300);
  const { data, fetchNextPage, hasNextPage } = useSessions(debounced);
  const createSession = useCreateSession();
  const updateSession = useUpdateSession();
  const deleteSession = useDeleteSession();
  const navigate = useNavigate();
  const { sessionId } = useParams();

  const items = data?.pages.flatMap((p) => p.items) ?? [];
  const groups = groupByDate(items);

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
      if (sessionId === id) navigate("/");
    }
  }

  return (
    <aside className="flex w-72 shrink-0 flex-col border-r">
      <div className="space-y-2 p-3">
        <Button className="w-full" onClick={onNew}>＋ 新建任务</Button>
        <Input placeholder="搜索会话…" value={query} onChange={(e) => setQuery(e.target.value)} />
      </div>
      <nav className="flex-1 overflow-y-auto px-2 pb-3">
        {groups.map((g) => (
          <div key={g.label}>
            <p className="px-2 pt-3 pb-1 text-xs text-muted-foreground">{g.label}</p>
            {g.items.map((s) => (
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
                <button className="hidden px-1 text-xs text-muted-foreground group-hover:block"
                        onClick={() => updateSession.mutate({ id: s.id, patch: { pinned: !s.pinned } })}>{s.pinned ? "取消" : "置顶"}</button>
                <button className="hidden px-1 text-xs text-muted-foreground group-hover:block"
                        onClick={() => updateSession.mutate({ id: s.id, patch: { archived: true } })}>归档</button>
                <button className="hidden px-1 text-xs text-red-500 group-hover:block"
                        onClick={() => onDelete(s.id)}>删</button>
              </div>
            ))}
          </div>
        ))}
        {hasNextPage && (
          <Button variant="ghost" size="sm" className="mt-2 w-full" onClick={() => fetchNextPage()}>
            加载更多
          </Button>
        )}
      </nav>
    </aside>
  );
}
