import { useState } from "react";
import { NavLink, useMatch, useNavigate } from "react-router-dom";
import {
  useBulkDeleteSessions,
  useCreateSession,
  useDeleteSession,
  useSessions,
  useUpdateSession,
  type SessionItem,
} from "@/api/sessions";
import { useAgents } from "@/api/agents";
import { groupByDate } from "@/lib/time";
import AgentAvatar from "@/components/agents/AgentAvatar";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ChevronDownIcon, PanelLeftClose, PanelLeftOpen, Plus } from "lucide-react";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { useUiStore } from "@/stores/ui";
import { toast } from "@/stores/toast";

/** 分组标题：多选模式下带"全选该组"复选框（部分选中显示 indeterminate）。 */
function GroupHeader({
  label,
  ids,
  selectable,
  selected,
  disabled,
  onToggle,
}: {
  label: string;
  ids: string[];
  selectable: boolean;
  selected: Set<string>;
  disabled: boolean;
  onToggle: (checked: boolean) => void;
}) {
  const all = ids.length > 0 && ids.every((id) => selected.has(id));
  const some = ids.some((id) => selected.has(id));
  return (
    <label
      data-testid={`session-group-${label}`}
      className="flex items-center gap-2 px-2 pt-3 pb-1 text-xs text-muted-foreground"
    >
      {selectable && (
        <input
          type="checkbox"
          aria-label={`全选 ${label}`}
          className="size-3.5 shrink-0 accent-primary"
          checked={all}
          ref={(el) => {
            if (el) el.indeterminate = some && !all;
          }}
          disabled={disabled}
          onChange={(e) => onToggle(e.target.checked)}
        />
      )}
      <span>{label}</span>
      <span>{ids.length}</span>
    </label>
  );
}

export default function SessionSidebar() {
  const [query, setQuery] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  // 多选模式：分组标题的复选框可整组选中；删除确认就近显示在按钮旁（不用弹窗）
  const [selectMode, setSelectMode] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirming, setConfirming] = useState(false);
  const theme = useUiStore((s) => s.theme);
  const toggleTheme = useUiStore((s) => s.toggleTheme);
  const thinkingDefaultOpen = useUiStore((s) => s.thinkingDefaultOpen);
  const setThinkingDefaultOpen = useUiStore((s) => s.setThinkingDefaultOpen);
  const sidebarCollapsed = useUiStore((s) => s.sidebarCollapsed);
  const setSidebarCollapsed = useUiStore((s) => s.setSidebarCollapsed);
  const debounced = useDebouncedValue(query, 300);
  const { data, fetchNextPage, hasNextPage } = useSessions(debounced, showArchived);
  const { data: agents = [] } = useAgents();
  const createSession = useCreateSession();
  const updateSession = useUpdateSession();
  const deleteSession = useDeleteSession();
  const bulkDelete = useBulkDeleteSessions();
  const navigate = useNavigate();
  // 用 location 匹配而非 useParams：sidebar 渲染在父路由元素中（Outlet 之外），
  // 显式匹配当前 URL 才能稳定拿到正在浏览的会话 id（不依赖路由嵌套层级）
  const match = useMatch("/sessions/:sessionId");
  const activeId = match?.params.sessionId;

  const items = data?.pages.flatMap((p) => p.items) ?? [];
  // 后端按 pinned desc 返回：置顶项单独成组（保持接口顺序），其余再做日期分组
  const pinnedItems = items.filter((s) => s.pinned);
  const groups = groupByDate(items.filter((s) => !s.pinned));

  function exitSelectMode() {
    setSelectMode(false);
    setSelected(new Set());
    setConfirming(false);
  }

  function setIds(ids: string[], checked: boolean) {
    setConfirming(false);
    setSelected((prev) => {
      const next = new Set(prev);
      for (const id of ids) {
        if (checked) next.add(id);
        else next.delete(id);
      }
      return next;
    });
  }

  function toggleSelected(id: string) {
    setConfirming(false);
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function runBulkDelete() {
    const ids = [...selected];
    if (ids.length === 0) return;
    try {
      const res = await bulkDelete.mutateAsync(ids);
      toast.success(`已删除 ${res.deleted} 个会话`);
      exitSelectMode();
      if (activeId && ids.includes(activeId)) navigate("/");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "删除失败");
    }
  }

  async function onNew() {
    const s = await createSession.mutateAsync();
    navigate(`/sessions/${s.id}`);
  }

  async function onNewAgent(agentId: string) {
    const s = await createSession.mutateAsync(agentId);
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
    if (selectMode) {
      return (
        <label
          key={s.id}
          className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-accent/50"
        >
          <input
            type="checkbox"
            aria-label={`选择 ${s.title}`}
            className="size-4 shrink-0 accent-primary"
            checked={selected.has(s.id)}
            disabled={bulkDelete.isPending}
            onChange={() => toggleSelected(s.id)}
          />
          <span className="min-w-0 flex-1 truncate">
            {s.pinned ? "📌 " : ""}
            {s.title}
          </span>
        </label>
      );
    }
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

  // 单个 aside 做 width 过渡：展开内容定宽 w-72 + 外层 overflow-hidden，
  // 收起时内容被裁剪滑出而非回流抖动；motion-safe 尊重减少动态偏好
  return (
    <aside
      aria-label={sidebarCollapsed ? "会话侧边栏（已收起）" : undefined}
      className={`flex shrink-0 flex-col overflow-hidden border-r motion-safe:transition-[width] motion-safe:duration-200 motion-safe:ease-in-out ${
        sidebarCollapsed ? "w-12" : "w-72"
      }`}
    >
      {sidebarCollapsed ? (
        // 收起态：只留窄栏（展开 + 新建两个图标），把横向空间还给对话区
        <div className="flex w-12 flex-col items-center gap-1 py-3">
          <Button
            variant="ghost"
            size="icon"
            aria-label="展开侧边栏"
            title="展开侧边栏"
            onClick={() => setSidebarCollapsed(false)}
          >
            <PanelLeftOpen />
          </Button>
          <Button variant="ghost" size="icon" aria-label="新建任务" title="新建任务" onClick={onNew}>
            <Plus />
          </Button>
        </div>
      ) : (
      <div className="flex min-h-0 w-72 flex-1 flex-col">
      <div className="space-y-2 p-3">
        <div className="flex gap-1">
          <Button
            variant="ghost"
            size="icon"
            aria-label="收起侧边栏"
            title="收起侧边栏"
            onClick={() => setSidebarCollapsed(true)}
          >
            <PanelLeftClose />
          </Button>
          <Button className="flex-1" onClick={onNew}>＋ 新建任务</Button>
          <DropdownMenu>
            <DropdownMenuTrigger
              className={buttonVariants({ variant: "outline", size: "icon" })}
              aria-label="选择智能体新建"
            >
              <ChevronDownIcon />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {agents.map((agent) => (
                <DropdownMenuItem key={agent.id} onClick={() => onNewAgent(agent.id)}>
                  <AgentAvatar
                    agentId={agent.id}
                    name={agent.name}
                    hasAvatar={agent.has_avatar}
                    version={agent.updated_at}
                    className="size-4 text-[9px]"
                  />
                  {agent.name}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
        <Input placeholder="搜索会话…" maxLength={64} value={query} onChange={(e) => setQuery(e.target.value)} />
        {selectMode && (
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="text-muted-foreground">已选 {selected.size}</span>
            {confirming ? (
              <>
                <span className="text-red-500">删除 {selected.size} 条？不可恢复</span>
                <Button
                  size="sm"
                  variant="destructive"
                  disabled={bulkDelete.isPending}
                  onClick={runBulkDelete}
                >
                  {bulkDelete.isPending ? "删除中…" : "确认删除"}
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setConfirming(false)}>
                  取消
                </Button>
              </>
            ) : (
              <Button
                size="sm"
                variant="destructive"
                disabled={selected.size === 0}
                onClick={() => setConfirming(true)}
              >
                删除选中
              </Button>
            )}
            <Button size="sm" variant="ghost" onClick={exitSelectMode}>
              退出
            </Button>
          </div>
        )}
      </div>
      <nav className="flex-1 overflow-y-auto px-2 pb-3">
        {pinnedItems.length > 0 && (
          <div>
            <GroupHeader
              label="置顶"
              ids={pinnedItems.map((s) => s.id)}
              selectable={selectMode}
              selected={selected}
              disabled={bulkDelete.isPending}
              onToggle={(checked) => setIds(pinnedItems.map((s) => s.id), checked)}
            />
            {pinnedItems.map(renderItem)}
          </div>
        )}
        {groups.map((g) => (
          <div key={g.label}>
            <GroupHeader
              label={g.label}
              ids={g.items.map((s) => s.id)}
              selectable={selectMode}
              selected={selected}
              disabled={bulkDelete.isPending}
              onToggle={(checked) => setIds(g.items.map((s) => s.id), checked)}
            />
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
        <NavLink
          to="/kb"
          className={({ isActive }) =>
            `block rounded px-2 py-1.5 text-sm ${isActive ? "bg-accent" : "hover:bg-accent/50"}`
          }
        >
          📚 知识库
        </NavLink>
        <NavLink
          to="/keys"
          className={({ isActive }) =>
            `block rounded px-2 py-1.5 text-sm ${isActive ? "bg-accent" : "hover:bg-accent/50"}`
          }
        >
          🔑 API 密钥
        </NavLink>
        <NavLink
          to="/capabilities"
          className={({ isActive }) =>
            `block rounded px-2 py-1.5 text-sm ${isActive ? "bg-accent" : "hover:bg-accent/50"}`
          }
        >
          🧩 扩展能力
        </NavLink>
        <NavLink
          to="/admin"
          className={({ isActive }) =>
            `block rounded px-2 py-1.5 text-sm ${isActive ? "bg-accent" : "hover:bg-accent/50"}`
          }
        >
          📊 可观测性
        </NavLink>
        <div className="flex gap-1">
          <Button
            variant="ghost"
            size="sm"
            className="flex-1"
            aria-label="切换主题"
            onClick={toggleTheme}
          >
            {theme === "dark" ? "☀️ 亮色" : "🌙 暗色"}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="flex-1"
            aria-label="默认展开思考链"
            onClick={() => setThinkingDefaultOpen(!thinkingDefaultOpen)}
          >
            🧠 {thinkingDefaultOpen ? "思考展开" : "思考折叠"}
          </Button>
        </div>
        <div className="flex gap-1">
          <Button
            variant={selectMode ? "secondary" : "ghost"}
            size="sm"
            className="flex-1"
            onClick={() => (selectMode ? exitSelectMode() : setSelectMode(true))}
          >
            {selectMode ? "取消多选" : "多选"}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="flex-1"
            onClick={() => {
              exitSelectMode();
              setShowArchived((v) => !v);
            }}
          >
            {showArchived ? "返回" : "查看归档"}
          </Button>
        </div>
      </div>
      </div>
      )}
    </aside>
  );
}
