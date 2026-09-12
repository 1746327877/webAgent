import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiJson } from "@/lib/api";

export interface KbItem {
  id: string;
  name: string;
  description: string | null;
  embedding_model: string;
  chunk_size: number;
  chunk_overlap: number;
  created_at: string;
}

export interface DocumentItem {
  id: string;
  kb_id: string;
  filename: string;
  file_type: string;
  size_bytes: number;
  status: string;
  error: string | null;
  chunk_count: number;
  created_at: string;
}

export function useKbs() {
  return useQuery({ queryKey: ["kbs"], queryFn: () => apiJson<KbItem[]>("/api/v1/kbs") });
}

export function useCreateKb() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: Pick<KbItem, "name"> & Partial<Pick<KbItem, "description">>) =>
      apiJson<KbItem>("/api/v1/kbs", { method: "POST", body: JSON.stringify(payload) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["kbs"] }),
  });
}

export function useDeleteKb() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      const res = await apiFetch(`/api/v1/kbs/${id}`, { method: "DELETE" });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(body.detail ?? `HTTP ${res.status}`);
      }
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["kbs"] }),
  });
}

export function useDocuments(kbId: string | undefined) {
  return useQuery({
    queryKey: ["documents", kbId],
    queryFn: () => apiJson<DocumentItem[]>(`/api/v1/kbs/${kbId}/documents`),
    enabled: Boolean(kbId),
    refetchInterval: (query) => {
      const docs = query.state.data as DocumentItem[] | undefined;
      const active = docs?.some((d) => !["ready", "failed"].includes(d.status));
      return active ? 2000 : false;
    },
  });
}

export function useUploadDocument(kbId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      const res = await apiFetch(`/api/v1/kbs/${kbId}/documents`, { method: "POST", body: form });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(body.detail ?? `HTTP ${res.status}`);
      }
      return (await res.json()) as DocumentItem;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["documents", kbId] }),
  });
}

export function useDeleteDocument(kbId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (docId: string) => {
      const res = await apiFetch(`/api/v1/kbs/${kbId}/documents/${docId}`, { method: "DELETE" });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(body.detail ?? `HTTP ${res.status}`);
      }
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["documents", kbId] }),
  });
}

export function useRetryDocument(kbId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (docId: string) =>
      apiJson<DocumentItem>(`/api/v1/kbs/${kbId}/documents/${docId}/retry`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["documents", kbId] }),
  });
}
