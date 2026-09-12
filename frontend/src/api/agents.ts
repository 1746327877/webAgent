import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiJson } from "@/lib/api";

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
  created_at: string;
  updated_at: string;
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

export function useModels() {
  return useQuery({
    queryKey: ["models"],
    queryFn: () => apiJson<{ name: string; size_mb: number | null }[]>("/api/v1/models"),
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
    queryFn: () =>
      apiJson<
        { id: string; slug: string; name: string; description: string; category: string; is_system: boolean }[]
      >("/api/v1/tools"),
  });
}
