import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiJson } from "@/lib/api";

export interface SessionItem {
  id: string;
  title: string;
  agent_id: string | null;
  pinned: boolean;
  archived: boolean;
  last_message_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface SessionsPage {
  items: SessionItem[];
  total: number;
}

export interface Block {
  type: string;
  content?: string;
  duration_ms?: number | null;
  [key: string]: unknown;
}

export interface AttachmentInfo {
  id: string;
  original_name?: string;
  kind?: string;
  mime_type?: string;
  size_bytes?: number;
}

export interface MessageItemData {
  id: string;
  role: string;
  agent_id?: string | null;
  blocks: Block[];
  status: string;
  rating: number | null;
  error: string | null;
  created_at: string;
  attachments?: AttachmentInfo[];
}

export function useSessions(query: string, archived = false) {
  return useInfiniteQuery({
    queryKey: ["sessions", query, archived],
    queryFn: ({ pageParam }) =>
      apiJson<SessionsPage>(
        `/api/v1/sessions?query=${encodeURIComponent(query)}&archived=${archived}&limit=50&offset=${pageParam}`,
      ),
    initialPageParam: 0,
    getNextPageParam: (last, pages) => {
      const loaded = pages.reduce((n, p) => n + p.items.length, 0);
      return loaded < last.total ? loaded : undefined;
    },
  });
}

export function useCreateSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (agentId?: string) =>
      apiJson<SessionItem>("/api/v1/sessions", {
        method: "POST",
        body: JSON.stringify(agentId ? { agent_id: agentId } : {}),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sessions"] }),
  });
}

export function useSession(id: string | undefined) {
  return useQuery({
    queryKey: ["session", id],
    queryFn: () => apiJson<SessionItem>(`/api/v1/sessions/${id}`),
    enabled: Boolean(id),
  });
}

export function useUpdateSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: Partial<Pick<SessionItem, "title" | "pinned" | "archived">> }) =>
      apiJson<SessionItem>(`/api/v1/sessions/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sessions"] }),
  });
}

export function useDeleteSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      const res = await apiFetch(`/api/v1/sessions/${id}`, { method: "DELETE" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sessions"] }),
  });
}

/** 多选删除：后端单请求上限 1000 条，超过则分批，最后汇总删除条数 */
export const BULK_DELETE_CHUNK = 500;

export function useBulkDeleteSessions() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (ids: string[]) => {
      let deleted = 0;
      for (let start = 0; start < ids.length; start += BULK_DELETE_CHUNK) {
        const chunk = ids.slice(start, start + BULK_DELETE_CHUNK);
        const res = await apiJson<{ deleted: number }>("/api/v1/sessions/bulk-delete", {
          method: "POST",
          body: JSON.stringify({ ids: chunk }),
        });
        deleted += res.deleted;
      }
      return { deleted };
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sessions"] }),
  });
}

export function useMessages(sessionId: string | undefined) {
  return useQuery({
    queryKey: ["messages", sessionId],
    queryFn: () => apiJson<MessageItemData[]>(`/api/v1/sessions/${sessionId}/messages`),
    enabled: Boolean(sessionId),
  });
}
