import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  useAgent,
  useCreateAgent,
  useDeleteAgent,
  usePublishAgent,
  useSetAgentMcpTools,
  useSetAgentSkills,
  useSetAgentTools,
  useTools,
  useUpdateAgent,
  useUploadAgentAvatar,
  type AgentItem,
  type McpToolBinding,
} from "@/api/agents";
import AgentAvatar from "@/components/agents/AgentAvatar";
import AgentForm from "@/components/agents/AgentForm";
import CapabilityBindings from "@/components/agents/CapabilityBindings";
import CapabilityDraftPanel, {
  type CapabilityDraft,
} from "@/components/agents/CapabilityDraftPanel";
import KbBindings from "@/components/agents/KbBindings";
import VersionsDrawer from "@/components/agents/VersionsDrawer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsPanel } from "@/components/ui/tabs";
import { toast } from "@/stores/toast";

const EDIT_TABS = [
  { key: "basic", label: "基础信息" },
  { key: "capabilities", label: "扩展能力" },
  { key: "knowledge", label: "知识库" },
] as const;

// 新建时还没有 agent id，知识库需创建后再绑定，故不展示该标签
const NEW_TABS = [
  { key: "basic", label: "基础信息" },
  { key: "capabilities", label: "扩展能力" },
] as const;

type EditTabKey = (typeof EDIT_TABS)[number]["key"];
type NewTabKey = (typeof NEW_TABS)[number]["key"];

export default function AgentEditorPage() {
  const { agentId } = useParams();
  const isNew = !agentId;
  const navigate = useNavigate();
  const { data: agent, isLoading, error: loadError } = useAgent(agentId);
  const { data: tools } = useTools();
  const createAgent = useCreateAgent();
  const updateAgent = useUpdateAgent();
  const deleteAgent = useDeleteAgent();
  const publishAgent = usePublishAgent();
  // 新建态的扩展能力：先在本页攒着，创建成功后串联保存
  const setTools = useSetAgentTools();
  const setSkills = useSetAgentSkills();
  const setMcpTools = useSetAgentMcpTools();
  const uploadAvatar = useUploadAgentAvatar();
  const [versionsOpen, setVersionsOpen] = useState(false);
  const [tab, setTab] = useState<EditTabKey>("basic");
  const [newTab, setNewTab] = useState<NewTabKey>("basic");
  const [draft, setDraft] = useState<CapabilityDraft>({
    skillSlugs: [],
    toolSlugs: [],
    mcpTools: [] as McpToolBinding[],
  });
  const [avatarFile, setAvatarFile] = useState<File | null>(null);

  const saving = createAgent.isPending || updateAgent.isPending;

  /** 新建成功后把草稿里的扩展能力/头像逐个写上去，失败的项明确告知 */
  async function persistDrafts(created: AgentItem) {
    const failures: string[] = [];
    if (draft.toolSlugs.length > 0) {
      try {
        await setTools.mutateAsync({ id: created.id, slugs: draft.toolSlugs });
      } catch {
        failures.push("工具绑定");
      }
    }
    if (draft.skillSlugs.length > 0) {
      try {
        await setSkills.mutateAsync({ id: created.id, slugs: draft.skillSlugs });
      } catch {
        failures.push("Skill 绑定");
      }
    }
    if (draft.mcpTools.length > 0) {
      try {
        await setMcpTools.mutateAsync({ id: created.id, tools: draft.mcpTools });
      } catch {
        failures.push("MCP 绑定");
      }
    }
    if (avatarFile) {
      try {
        await uploadAvatar.mutateAsync({ id: created.id, file: avatarFile });
      } catch {
        failures.push("头像");
      }
    }
    if (failures.length > 0) {
      toast.error(`智能体已创建，但以下未保存成功：${failures.join("、")}，可进编辑器重试`);
    } else {
      toast.success("智能体已创建");
    }
  }

  async function onSubmit(payload: Partial<AgentItem>) {
    try {
      if (isNew) {
        const created = await createAgent.mutateAsync(payload);
        await persistDrafts(created);
        navigate(`/agents/${created.id}`);
      } else {
        await updateAgent.mutateAsync({ id: agentId, patch: payload });
        toast.success("已保存");
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "保存失败");
    }
  }

  async function onPublish() {
    if (!agentId) return;
    try {
      const res = await publishAgent.mutateAsync(agentId);
      toast.success(`已发布 v${res.version}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "发布失败");
    }
  }

  async function onDelete() {
    if (!agentId || !window.confirm("删除该智能体？该操作不可恢复。")) return;
    try {
      await deleteAgent.mutateAsync(agentId);
      toast.success("智能体已删除");
      navigate("/agents");
    } catch (err) {
      // 409（已被会话使用）等错误由服务端 detail 展示
      toast.error(err instanceof Error ? err.message : "删除失败");
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
        <Link to="/agents" className="text-sm underline">
          返回列表
        </Link>
      </div>
    );
  }

  const formKey = isNew ? "new" : `form:${agentId}:${agent?.updated_at ?? ""}`;

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto max-w-3xl space-y-5 p-6">
        <div className="flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <Link to="/agents" className="shrink-0 text-sm text-muted-foreground hover:underline">
              ← 返回
            </Link>
            {isNew ? (
              <h1 className="truncate text-xl font-semibold">新建智能体</h1>
            ) : (
              <div className="flex min-w-0 items-center gap-2">
                <AgentAvatar
                  agentId={agent?.id}
                  name={agent?.name ?? ""}
                  hasAvatar={Boolean(agent?.has_avatar)}
                  version={agent?.updated_at}
                  className="size-7 text-xs"
                />
                <h1 className="truncate text-xl font-semibold">{agent?.name}</h1>
              </div>
            )}
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

        {isNew && (
          <>
            <Tabs
              value={newTab}
              onChange={(key) => setNewTab(key as NewTabKey)}
              items={NEW_TABS}
              ariaLabel="智能体编辑分区"
            />
            {/* 基础信息保持挂载（hidden 切换），避免切标签丢失未保存的表单草稿 */}
            <div className={newTab === "basic" ? "block" : "hidden"}>
              <AgentForm
                key={formKey}
                onSubmit={onSubmit}
                saving={saving}
                onAvatarChange={setAvatarFile}
              />
            </div>
            {newTab === "capabilities" && (
              <TabsPanel>
                <CapabilityDraftPanel
                  tools={tools ?? []}
                  draft={draft}
                  onChange={(patch) => setDraft((prev) => ({ ...prev, ...patch }))}
                  disabled={saving}
                />
              </TabsPanel>
            )}
          </>
        )}

        {!isNew && agent && (
          <>
            <Tabs
              value={tab}
              onChange={(key) => setTab(key as EditTabKey)}
              items={EDIT_TABS}
              ariaLabel="智能体编辑分区"
            />

            <div className={tab === "basic" ? "block" : "hidden"}>
              <AgentForm key={formKey} initial={agent} onSubmit={onSubmit} saving={saving} />
            </div>

            {tab === "capabilities" && (
              <TabsPanel>
                <CapabilityBindings
                  key={`caps:${agent.id}:${agent.updated_at}`}
                  agent={agent}
                  tools={tools ?? []}
                  onNotice={(message) => toast.success(message)}
                  onError={(message) => toast.error(message)}
                />
              </TabsPanel>
            )}

            {tab === "knowledge" && (
              <TabsPanel>
                <KbBindings
                  key={`kb:${agent.id}:${agent.updated_at}`}
                  agentId={agent.id}
                  bindings={agent.kb_bindings ?? []}
                  editable
                  onNotice={(message) => toast.success(message)}
                  onError={(message) => toast.error(message)}
                />
              </TabsPanel>
            )}
          </>
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
