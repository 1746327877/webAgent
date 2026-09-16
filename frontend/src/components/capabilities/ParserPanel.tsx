import { useParserStatus } from "@/api/capabilities";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline gap-2">
      <dt className="w-20 shrink-0 text-xs text-muted-foreground">{label}</dt>
      <dd className="min-w-0 flex-1 break-all">{value}</dd>
    </div>
  );
}

export default function ParserPanel() {
  const { data, isLoading, error } = useParserStatus();

  if (isLoading) return <p className="text-sm text-muted-foreground">加载中…</p>;
  if (error) return <p className="text-sm text-red-500">{error.message}</p>;
  if (!data) return null;

  const statusBadge = data.healthy ? (
    <Badge>服务正常</Badge>
  ) : data.enabled ? (
    <Badge variant="destructive">连接失败</Badge>
  ) : (
    <Badge variant="secondary">未启用</Badge>
  );

  return (
    <Card>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">MinerU 文档解析</span>
          {statusBadge}
          {data.version && <Badge variant="outline">v{data.version}</Badge>}
        </div>

        <dl className="space-y-1.5">
          <Row label="解析后端" value={data.backend} />
          <Row label="服务地址" value={data.api_url ?? "未配置"} />
          <Row
            label="健康探测"
            value={data.latency_ms != null ? `${data.latency_ms} ms` : "-"}
          />
          <Row label="生效范围" value="PDF / DOCX（含扫描件 OCR）；其余类型走内置解析" />
        </dl>

        {data.error && <p className="text-xs text-red-500">{data.error}</p>}

        <p className="text-xs text-muted-foreground">
          未启用或服务不可用时，知识库解析自动回退内置 pymupdf/docx（无 OCR），不影响使用。
          启动服务：在宿主机运行 <code>scripts/start-mineru.ps1</code>。
        </p>
      </CardContent>
    </Card>
  );
}
