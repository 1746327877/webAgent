import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiJson } from "@/lib/api";

export interface SessionItem {
  id: string;
  title: string;
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

export interface MessageItemData {
  id: string;
  role: string;
  blocks: Block[];
  status: string;
  rating: number | null;
  created_at: string;
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
    mutationFn: () => apiJson<SessionItem>("/api/v1/sessions", { method: "POST", body: "{}" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sessions"] }),
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

export function useMessages(sessionId: string | undefined) {
  return useQuery({
    queryKey: ["messages", sessionId],
    queryFn: () => apiJson<MessageItemData[]>(`/api/v1/sessions/${sessionId}/messages`),
    enabled: Boolean(sessionId),
  });
}
