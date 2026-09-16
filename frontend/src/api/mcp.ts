import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiJson } from "@/lib/api";

export type McpTransport = "http" | "stdio";
export type McpStatus = "unknown" | "ok" | "error";

export interface McpTool {
  name: string;
  description: string;
}

export interface McpServer {
  id: string;
  name: string;
  transport: McpTransport;
  url: string | null;
  headers: Record<string, string>;
  command: string | null;
  args: string[];
  env: Record<string, string>;
  enabled: boolean;
  status: McpStatus;
  last_error: string | null;
  tools: McpTool[];
  last_checked_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface McpConfigInput {
  name: string;
  transport: McpTransport;
  url?: string | null;
  headers?: Record<string, string>;
  command?: string | null;
  args?: string[];
  env?: Record<string, string>;
  enabled?: boolean;
}

export interface McpProbeResult {
  ok: boolean;
  tools: McpTool[];
  error: string | null;
  latency_ms: number | null;
  server?: McpServer;
}

export function useMcpServers() {
  return useQuery({
    queryKey: ["mcp-servers"],
    queryFn: () => apiJson<McpServer[]>("/api/v1/mcp-servers"),
  });
}

export function useCreateMcpServer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: McpConfigInput) =>
      apiJson<McpServer>("/api/v1/mcp-servers", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["mcp-servers"] }),
  });
}

export function useUpdateMcpServer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: McpConfigInput }) =>
      apiJson<McpServer>(`/api/v1/mcp-servers/${id}`, {
        method: "PATCH",
        body: JSON.stringify(patch),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["mcp-servers"] }),
  });
}

export function useDeleteMcpServer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      const res = await apiFetch(`/api/v1/mcp-servers/${id}`, { method: "DELETE" });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(body.detail ?? `HTTP ${res.status}`);
      }
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["mcp-servers"] }),
  });
}

/** 用表单里的配置探测，不落库（保存前「测试连接」） */
export function useProbeMcpConfig() {
  return useMutation({
    mutationFn: (payload: McpConfigInput) =>
      apiJson<McpProbeResult>("/api/v1/mcp-servers/test", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
  });
}

/** 测试已保存的 MCP，并写回状态与工具列表 */
export function useTestMcpServer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiJson<McpProbeResult>(`/api/v1/mcp-servers/${id}/test`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["mcp-servers"] }),
  });
}
