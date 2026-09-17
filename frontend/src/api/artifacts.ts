import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiJson } from "@/lib/api";

/** 与后端 app/api/v1/artifacts.py 的 ArtifactOut 字段一致 */
export interface ArtifactInfo {
  id: string;
  session_id: string;
  /** export=平台导出 / tool=内置工具 / mcp=MCP */
  source: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  created_at: string;
}

export function useArtifacts(sessionId?: string) {
  return useQuery({
    queryKey: ["artifacts", sessionId],
    queryFn: () => apiJson<ArtifactInfo[]>(`/api/v1/sessions/${sessionId}/artifacts`),
    enabled: Boolean(sessionId) && sessionId !== "new",
  });
}

/** 把当前会话导出成 Markdown 产物；成功后刷新产物列表 */
export function useExportMarkdown(sessionId?: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiJson<ArtifactInfo>(`/api/v1/sessions/${sessionId}/artifacts/markdown`, {
        method: "POST",
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["artifacts", sessionId] });
    },
  });
}

export function artifactFileUrl(id: string): string {
  return `/api/v1/artifacts/${id}`;
}

/** 产物下载要走鉴权（apiFetch 带 token），所以用 blob + 临时 <a> 触发保存 */
export async function downloadArtifact(artifact: ArtifactInfo): Promise<void> {
  const res = await apiFetch(artifactFileUrl(artifact.id));
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = artifact.filename;
  link.click();
  URL.revokeObjectURL(url);
}
