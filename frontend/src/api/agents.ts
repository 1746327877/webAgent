import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiErrorMessage, apiFetch, apiJson } from "@/lib/api";

export interface KbBinding {
  kb_id: string;
  name: string;
  top_k: number;
  score_threshold: number;
}

export interface KbBindingInput {
  kb_id: string;
  top_k: number;
  score_threshold?: number;
}

export interface AgentItem {
  id: string;
  name: string;
  emoji: string;
  description: string | null;
  tags: string[];
  system_prompt: string;
  model_config: Record<string, unknown>;
  welcome_msg: string | null;
  examples: string[];
  status: string;
  current_version: number;
  variables: string[];
  tool_slugs: string[];
  skill_slugs: string[];
  mcp_tools: McpToolBinding[];
  kb_bindings: KbBinding[];
  has_avatar: boolean;
  created_at: string;
  updated_at: string;
}

export interface McpToolBinding {
  mcp_server_id: string;
  tool_name: string;
}

/** 展示用精简智能体信息（头像 + 名字），供消息徽标/提及列表等复用 */
export type AgentBadge = Pick<AgentItem, "id" | "name" | "has_avatar" | "updated_at">;

export function toAgentBadge(agent: AgentItem): AgentBadge {
  return {
    id: agent.id,
    name: agent.name,
    has_avatar: agent.has_avatar,
    updated_at: agent.updated_at,
  };
}

export interface ToolInfo {
  id: string;
  slug: string;
  name: string;
  description: string;
  category: string;
  is_system: boolean;
  input_schema?: {
    properties?: Record<string, { type?: string; title?: string; default?: unknown }>;
    required?: string[];
  };
}

export interface AgentVersion {
  version: number;
  snapshot: Record<string, unknown>;
  created_at: string;
}

export function useAgents() {
  return useQuery({ queryKey: ["agents"], queryFn: () => apiJson<AgentItem[]>("/api/v1/agents") });
}

export function useAgent(id: string | undefined) {
  return useQuery({
    queryKey: ["agents", id],
    queryFn: () => apiJson<AgentItem>(`/api/v1/agents/${id}`),
    enabled: Boolean(id),
  });
}

export interface ModelInfo {
  name: string;
  size_mb: number | null;
  /** Ollama 能力标签，如 ["completion","tools","thinking"]；空数组表示未能探测 */
  capabilities?: string[];
}

export function useModels() {
  return useQuery({
    queryKey: ["models"],
    queryFn: () => apiJson<ModelInfo[]>("/api/v1/models"),
  });
}

export function useCreateAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: Partial<AgentItem>) =>
      apiJson<AgentItem>("/api/v1/agents", { method: "POST", body: JSON.stringify(payload) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agents"] }),
  });
}

export function useUpdateAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: Partial<AgentItem> }) =>
      apiJson<AgentItem>(`/api/v1/agents/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agents"] }),
  });
}

export function useDeleteAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      const res = await apiFetch(`/api/v1/agents/${id}`, { method: "DELETE" });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(body.detail ?? `HTTP ${res.status}`);
      }
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agents"] }),
  });
}

export function useTools() {
  return useQuery({
    queryKey: ["tools"],
    queryFn: () => apiJson<ToolInfo[]>("/api/v1/tools"),
  });
}

/** 上传/替换智能体头像（图片 ≤ 2MB；替换时后端删除旧文件） */
export function useUploadAgentAvatar() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, file }: { id: string; file: File }) => {
      const form = new FormData();
      form.append("file", file);
      const res = await apiFetch(`/api/v1/agents/${id}/avatar`, { method: "POST", body: form });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(apiErrorMessage(body, res.status));
      }
      return (await res.json()) as AgentItem;
    },
    onSuccess: (_data, { id }) => {
      qc.invalidateQueries({ queryKey: ["agents", id] });
      qc.invalidateQueries({ queryKey: ["agents"] });
    },
  });
}

/** 移除智能体头像（前端随即回退到"名字首字"） */
export function useDeleteAgentAvatar() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      const res = await apiFetch(`/api/v1/agents/${id}/avatar`, { method: "DELETE" });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(apiErrorMessage(body, res.status));
      }
    },
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: ["agents", id] });
      qc.invalidateQueries({ queryKey: ["agents"] });
    },
  });
}

export function useSetAgentTools() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, slugs }: { id: string; slugs: string[] }) =>
      apiJson<{ slugs: string[] }>(`/api/v1/agents/${id}/tools`, {
        method: "PUT",
        body: JSON.stringify({ slugs }),
      }),
    onSuccess: (_data, { id }) => {
      qc.invalidateQueries({ queryKey: ["agents", id] });
      qc.invalidateQueries({ queryKey: ["agents"] });
    },
  });
}

export function useSetAgentSkills() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, slugs }: { id: string; slugs: string[] }) =>
      apiJson<{ slugs: string[] }>(`/api/v1/agents/${id}/skills`, {
        method: "PUT",
        body: JSON.stringify({ slugs }),
      }),
    onSuccess: (_data, { id }) => {
      qc.invalidateQueries({ queryKey: ["agents", id] });
      qc.invalidateQueries({ queryKey: ["agents"] });
    },
  });
}

export function useSetAgentMcpTools() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, tools }: { id: string; tools: McpToolBinding[] }) =>
      apiJson<{ tools: McpToolBinding[] }>(`/api/v1/agents/${id}/mcp-tools`, {
        method: "PUT",
        body: JSON.stringify({ tools }),
      }),
    onSuccess: (_data, { id }) => {
      qc.invalidateQueries({ queryKey: ["agents", id] });
      qc.invalidateQueries({ queryKey: ["agents"] });
    },
  });
}

export function useSetAgentKbs() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ agentId, bindings }: { agentId: string; bindings: KbBindingInput[] }) =>
      apiJson<{ bindings: KbBinding[] }>(`/api/v1/agents/${agentId}/kbs`, {
        method: "PUT",
        body: JSON.stringify({ bindings }),
      }),
    onSuccess: (_data, { agentId }) => {
      qc.invalidateQueries({ queryKey: ["agents", agentId] });
      qc.invalidateQueries({ queryKey: ["agents"] });
    },
  });
}

export function usePublishAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiJson<{ version: number; status: string }>(`/api/v1/agents/${id}/publish`, {
        method: "POST",
      }),
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: ["agents", id] });
      qc.invalidateQueries({ queryKey: ["agents"] });
      qc.invalidateQueries({ queryKey: ["agent-versions", id] });
    },
  });
}

export function useAgentVersions(id: string | undefined) {
  return useQuery({
    queryKey: ["agent-versions", id],
    queryFn: () => apiJson<AgentVersion[]>(`/api/v1/agents/${id}/versions`),
    enabled: Boolean(id),
  });
}

export function useRollbackAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, version }: { id: string; version: number }) =>
      apiJson<AgentItem>(`/api/v1/agents/${id}/rollback`, {
        method: "POST",
        body: JSON.stringify({ version }),
      }),
    onSuccess: (_data, { id }) => {
      qc.invalidateQueries({ queryKey: ["agents", id] });
      qc.invalidateQueries({ queryKey: ["agents"] });
      qc.invalidateQueries({ queryKey: ["agent-versions", id] });
    },
  });
}
