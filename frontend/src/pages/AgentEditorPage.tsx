import { useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import {
  useAgent,
  useCreateAgent,
  useDeleteAgent,
  usePublishAgent,
  useSetAgentTools,
  useTools,
  useUpdateAgent,
  type AgentItem,
  type ToolInfo,
} from "@/api/agents";
import AgentForm from "@/components/agents/AgentForm";
import ToolsMatrix from "@/components/agents/ToolsMatrix";
import VersionsDrawer from "@/components/agents/VersionsDrawer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

function ToolBindings({
  agent,
  tools,
  onNotice,
  onError,
}: {
  agent: AgentItem;
  tools: ToolInfo[];
  onNotice: (message: string) => void;
  onError: (message: string) => void;
}) {
  const initial = agent.tool_slugs ?? [];
  const setTools = useSetAgentTools();
  const [draft, setDraft] = useState<string[]>(initial);
  const dirty = [...draft].sort().join(",") !== [...initial].sort().join(",");

  async function onSave() {
    try {
      const res = await setTools.mutateAsync({ id: agent.id, slugs: draft });
      setDraft(res.slugs ?? []);
      onNotice("工具绑定已保存");
    } catch (err) {
      onError(err instanceof Error ? err.message : "保存工具绑定失败");
    }
  }

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-medium">工具绑定</h2>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={setTools.isPending || !dirty}
          onClick={onSave}
        >
          {setTools.isPending ? "保存中…" : "保存工具绑定"}
        </Button>
      </div>
      <ToolsMatrix tools={tools} value={draft} onChange={setDraft} disabled={setTools.isPending} />
    </section>
  );
}

export default function AgentEditorPage() {
  const { agentId } = useParams();
  const isNew = !agentId;
  const navigate = useNavigate();
  const location = useLocation();
  const { data: agent, isLoading, error: loadError } = useAgent(agentId);
  const { data: tools } = useTools();
  const createAgent = useCreateAgent();
  const updateAgent = useUpdateAgent();
  const deleteAgent = useDeleteAgent();
  const publishAgent = usePublishAgent();
  const justCreated = Boolean((location.state as { created?: boolean } | null)?.created);
  const [notice, setNotice] = useState<string | null>(justCreated ? "已创建" : null);
  const [error, setError] = useState<string | null>(null);
  const [versionsOpen, setVersionsOpen] = useState(false);

  const saving = createAgent.isPending || updateAgent.isPending;

  async function onSubmit(payload: Partial<AgentItem>) {
    setNotice(null);
    setError(null);
    try {
      if (isNew) {
        const created = await createAgent.mutateAsync(payload);
        navigate(`/agents/${created.id}`, { state: { created: true } });
      } else {
        await updateAgent.mutateAsync({ id: agentId, patch: payload });
        setNotice("已保存");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    }
  }

  async function onPublish() {
    if (!agentId) return;
    setNotice(null);
    setError(null);
    try {
      const res = await publishAgent.mutateAsync(agentId);
      setNotice(`已发布 v${res.version}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "发布失败");
    }
  }

  async function onDelete() {
    if (!agentId || !window.confirm("删除该智能体？该操作不可恢复。")) return;
    setNotice(null);
    setError(null);
    try {
      await deleteAgent.mutateAsync(agentId);
      navigate("/agents");
    } catch (err) {
      // 409（已被会话使用）等错误由服务端 detail 展示
      setError(err instanceof Error ? err.message : "删除失败");
    }
  }

  if (!isNew && isLoading) {
    return <div className="p-6 text-sm text-muted-foreground">加载中…</div>;
  }
  if (!isNew && (loadError || !agent)) {
    return (
      <div className="space-y-3 p-6">
        <p className="text-sm text-red-500">
          {loadError instanceof Error ? loadError.message : "智能体不存在"}
        </p>
        <Link to="/agents" className="text-sm underline">返回列表</Link>
      </div>
    );
  }

  const title = isNew ? "新建智能体" : agent ? `${agent.emoji} ${agent.name}` : "编辑智能体";

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto max-w-3xl space-y-5 p-6">
        <div className="flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <Link to="/agents" className="shrink-0 text-sm text-muted-foreground hover:underline">
              ← 返回
            </Link>
            <h1 className="truncate text-xl font-semibold">{title}</h1>
            {!isNew && agent && (
              <>
                <Badge variant={agent.status === "published" ? "default" : "secondary"}>
                  {agent.status === "published" ? "已发布" : "草稿"}
                </Badge>
                <span className="shrink-0 text-xs text-muted-foreground">
                  v{agent.current_version}
                </span>
              </>
            )}
          </div>
          {!isNew && (
            <div className="flex shrink-0 items-center gap-2">
              <Button variant="outline" size="sm" onClick={() => setVersionsOpen(true)}>
                版本
              </Button>
              <Button size="sm" onClick={onPublish} disabled={publishAgent.isPending}>
                {publishAgent.isPending ? "发布中…" : "发布"}
              </Button>
              <Button
                variant="destructive"
                size="sm"
                onClick={onDelete}
                disabled={deleteAgent.isPending}
              >
                删除
              </Button>
            </div>
          )}
        </div>

        {notice && <p className="text-sm text-green-600">{notice}</p>}
        {error && <p className="text-sm text-red-500">{error}</p>}

        <AgentForm
          key={isNew ? "new" : `form:${agentId}:${agent?.updated_at ?? ""}`}
          initial={isNew ? undefined : agent}
          onSubmit={onSubmit}
          saving={saving}
        />

        {!isNew && agent && (
          <ToolBindings
            key={`${agent.id}:${agent.updated_at}`}
            agent={agent}
            tools={tools ?? []}
            onNotice={(message) => {
              setError(null);
              setNotice(message);
            }}
            onError={(message) => {
              setNotice(null);
              setError(message);
            }}
          />
        )}

        {!isNew && agentId && (
          <VersionsDrawer
            agentId={agentId}
            open={versionsOpen}
            onClose={() => setVersionsOpen(false)}
          />
        )}
      </div>
    </div>
  );
}
