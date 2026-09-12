import { useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { Link, useParams } from "react-router-dom";
import {
  useDeleteDocument,
  useDocuments,
  useKbs,
  useRetryDocument,
  useUploadDocument,
} from "@/api/kbs";
import DocumentTable from "@/components/kb/DocumentTable";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

export default function KbDetailPage() {
  const { kbId } = useParams();
  const { data: kbs, isLoading: kbsLoading } = useKbs();
  const kb = kbs?.find((k) => k.id === kbId);
  const { data: documents = [], isLoading, error: loadError } = useDocuments(kbId);
  const uploadDocument = useUploadDocument(kbId ?? "");
  const deleteDocument = useDeleteDocument(kbId ?? "");
  const retryDocument = useRetryDocument(kbId ?? "");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);

  async function upload(file: File) {
    setMessage(null);
    setError(null);
    try {
      await uploadDocument.mutateAsync(file);
      setMessage(`已上传「${file.name}」，正在处理…`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "上传失败");
    }
  }

  function onPick(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (file) void upload(file);
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragActive(false);
    const file = e.dataTransfer.files?.[0];
    if (file) void upload(file);
  }

  async function onRetry(docId: string) {
    setMessage(null);
    setError(null);
    try {
      await retryDocument.mutateAsync(docId);
      setMessage("已重新提交解析");
    } catch (err) {
      setError(err instanceof Error ? err.message : "重试失败");
    }
  }

  async function onDelete(docId: string) {
    if (!window.confirm("删除该文档？该操作不可恢复。")) return;
    setMessage(null);
    setError(null);
    try {
      await deleteDocument.mutateAsync(docId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除失败");
    }
  }

  if (kbsLoading) {
    return <div className="p-6 text-sm text-muted-foreground">加载中…</div>;
  }
  if (!kb) {
    return (
      <div className="space-y-3 p-6">
        <p className="text-sm text-red-500">知识库不存在</p>
        <Link to="/kb" className="text-sm underline">返回列表</Link>
      </div>
    );
  }

  const processing = documents.some((d) => !["ready", "failed"].includes(d.status));

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto max-w-4xl space-y-5 p-6">
        <div className="flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <Link to="/kb" className="shrink-0 text-sm text-muted-foreground hover:underline">
              ← 返回
            </Link>
            <h1 className="truncate text-xl font-semibold">📚 {kb.name}</h1>
            {processing && <Badge variant="secondary">处理中…</Badge>}
          </div>
        </div>
        {kb.description && <p className="text-sm text-muted-foreground">{kb.description}</p>}

        <div
          className={`flex flex-col items-center gap-2 rounded-lg border border-dashed p-6 text-center transition-colors ${
            dragActive ? "border-primary bg-accent/40" : ""
          }`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragActive(true);
          }}
          onDragLeave={() => setDragActive(false)}
          onDrop={onDrop}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.md,.txt,.docx"
            className="hidden"
            onChange={onPick}
          />
          <p className="text-sm">拖拽文件到此处，或</p>
          <Button
            variant="outline"
            size="sm"
            disabled={uploadDocument.isPending}
            onClick={() => fileInputRef.current?.click()}
          >
            {uploadDocument.isPending ? "上传中…" : "选择文件上传"}
          </Button>
          <p className="text-xs text-muted-foreground">支持 .pdf / .md / .txt / .docx，最大 20MB</p>
        </div>

        {message && <p className="text-sm text-green-600">{message}</p>}
        {error && <p className="text-sm text-red-500">{error}</p>}
        {loadError && <p className="text-sm text-red-500">{loadError.message}</p>}

        {isLoading ? (
          <p className="text-sm text-muted-foreground">加载中…</p>
        ) : (
          <DocumentTable documents={documents} onRetry={onRetry} onDelete={onDelete} />
        )}
      </div>
    </div>
  );
}
