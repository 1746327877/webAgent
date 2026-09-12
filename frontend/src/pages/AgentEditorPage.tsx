import { useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import {
  useAgent,
  useCreateAgent,
  useDeleteAgent,
  useUpdateAgent,
  type AgentItem,
} from "@/api/agents";
import AgentForm from "@/components/agents/AgentForm";
import { Button } from "@/components/ui/button";

export default function AgentEditorPage() {
  const { agentId } = useParams();
  const isNew = !agentId;
  const navigate = useNavigate();
  const location = useLocation();
  const { data: agent, isLoading, error: loadError } = useAgent(agentId);
  const createAgent = useCreateAgent();
  const updateAgent = useUpdateAgent();
  const deleteAgent = useDeleteAgent();
  const justCreated = Boolean((location.state as { created?: boolean } | null)?.created);
  const [notice, setNotice] = useState<string | null>(justCreated ? "已创建" : null);
  const [error, setError] = useState<string | null>(null);

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
          </div>
          {!isNew && (
            <Button variant="destructive" size="sm" onClick={onDelete} disabled={deleteAgent.isPending}>
              删除
            </Button>
          )}
        </div>

        {notice && <p className="text-sm text-green-600">{notice}</p>}
        {error && <p className="text-sm text-red-500">{error}</p>}

        <AgentForm
          key={agentId ?? "new"}
          initial={isNew ? undefined : agent}
          onSubmit={onSubmit}
          saving={saving}
        />
      </div>
    </div>
  );
}
