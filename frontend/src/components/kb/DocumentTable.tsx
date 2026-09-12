import type { DocumentItem } from "@/api/kbs";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

const STATUS_LABEL: Record<string, string> = {
  pending: "处理中",
  parsing: "处理中",
  chunking: "处理中",
  embedding: "处理中",
  ready: "就绪",
  failed: "失败",
};

function statusLabel(status: string): string {
  return STATUS_LABEL[status] ?? status;
}

function statusVariant(status: string): "default" | "secondary" | "destructive" {
  if (status === "ready") return "default";
  if (status === "failed") return "destructive";
  return "secondary";
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export default function DocumentTable({
  documents,
  onRetry,
  onDelete,
}: {
  documents: DocumentItem[];
  onRetry: (docId: string) => void;
  onDelete: (docId: string) => void;
}) {
  if (documents.length === 0) {
    return <p className="text-sm text-muted-foreground">还没有文档，上传一个开始构建知识库。</p>;
  }

  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full text-left text-sm">
        <thead className="border-b bg-muted/50 text-xs text-muted-foreground">
          <tr>
            <th className="px-3 py-2 font-medium">文件名</th>
            <th className="px-3 py-2 font-medium">类型</th>
            <th className="px-3 py-2 font-medium">大小</th>
            <th className="px-3 py-2 font-medium">状态</th>
            <th className="px-3 py-2 font-medium">分块</th>
            <th className="px-3 py-2 font-medium">上传时间</th>
            <th className="px-3 py-2 text-right font-medium">操作</th>
          </tr>
        </thead>
        <tbody>
          {documents.map((doc) => (
            <tr key={doc.id} className="border-b last:border-b-0">
              <td className="max-w-[16rem] px-3 py-2">
                <p className="truncate" title={doc.filename}>{doc.filename}</p>
                {doc.status === "failed" && doc.error && (
                  <p className="mt-0.5 truncate text-xs text-red-500" title={doc.error}>
                    {doc.error}
                  </p>
                )}
              </td>
              <td className="px-3 py-2 text-muted-foreground">{doc.file_type}</td>
              <td className="px-3 py-2 text-muted-foreground">{formatBytes(doc.size_bytes)}</td>
              <td className="px-3 py-2">
                <Badge variant={statusVariant(doc.status)}>{statusLabel(doc.status)}</Badge>
              </td>
              <td className="px-3 py-2 text-muted-foreground">{doc.chunk_count}</td>
              <td className="px-3 py-2 text-xs text-muted-foreground">
                {new Date(doc.created_at).toLocaleString()}
              </td>
              <td className="px-3 py-2">
                <div className="flex justify-end gap-1.5">
                  {doc.status === "failed" && (
                    <Button variant="outline" size="sm" onClick={() => onRetry(doc.id)}>
                      重试
                    </Button>
                  )}
                  <Button variant="ghost" size="sm" className="text-red-500" onClick={() => onDelete(doc.id)}>
                    删除
                  </Button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
