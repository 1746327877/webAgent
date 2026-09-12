import { useQuery } from "@tanstack/react-query";
import { apiFetch, apiJson } from "@/lib/api";

export interface MetricsCards {
  llm_calls: number;
  errors: number;
  error_rate: number;
  p95_ms: number;
  prompt_tokens: number;
  completion_tokens: number;
  gpu_ms: number;
  model_switches: number;
  switch_ms: number;
  tool_calls: number;
  tool_error_rate: number;
  retrieval_calls: number;
  retrieval_avg_ms: number;
  http_requests: number;
  http_error_rate: number;
}

export interface MetricsSeriesPoint {
  hour: string;
  llm_calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  p95_ms: number;
  errors: number;
}

export interface MetricsAgent {
  agent_id: string;
  name: string | null;
  llm_calls: number;
  tokens: number;
}

export interface MetricsModel {
  model: string;
  llm_calls: number;
  tokens: number;
}

export interface MetricsTool {
  tool: string;
  calls: number;
  errors: number;
  avg_ms: number;
}

export interface MetricsSwitch {
  from_model: string | null;
  to_model: string | null;
  count: number;
  avg_ms: number;
}

export interface MetricsRetrieval {
  calls: number;
  errors: number;
  avg_ms: number;
}

export interface MetricsHttpPoint {
  bucket: string;
  requests: number;
  errors: number;
  avg_ms: number;
}

export interface MetricsHttp {
  requests: number;
  errors: number;
  error_rate: number;
  avg_ms: number;
  series: MetricsHttpPoint[];
}

export interface MetricsVramPoint {
  ts: string;
  vram_mb: number;
}

export interface MetricsOverview {
  hours: number;
  cards: MetricsCards;
  series: MetricsSeriesPoint[];
  agents: MetricsAgent[];
  models: MetricsModel[];
  tools: MetricsTool[];
  switches: MetricsSwitch[];
  retrieval: MetricsRetrieval;
  http: MetricsHttp;
  vram: MetricsVramPoint[];
}

export function useMetricsOverview(hours: number) {
  return useQuery({
    queryKey: ["admin-metrics", hours],
    queryFn: () => apiJson<MetricsOverview>(`/api/v1/admin/metrics/overview?hours=${hours}`),
    refetchInterval: 30000,
  });
}

/** 与后端 trace_service._span_view 逐字段一致 */
export interface SpanItem {
  id: string;
  parent_span_id: string | null;
  type: string;
  name: string | null;
  status: string;
  model: string | null;
  error: string | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  duration_ms: number | null;
  started_at: string;
  ended_at: string | null;
  session_id?: string | null;
  message_id?: string | null;
  agent_id?: string | null;
  input?: unknown;
  output?: unknown;
}

export interface TraceMessage {
  id: string;
  model: string | null;
  status: string;
  usage: unknown;
}

export interface MessageTrace {
  trace_id: string;
  message: TraceMessage;
  spans: SpanItem[];
}

export interface SpanLogPage {
  items: SpanItem[];
  total: number;
}

export type SpanFilters = Record<string, string | number | undefined>;

/** 过滤空值（""/"全部"）后再拼 query，保证列表与导出使用同一套筛选语义 */
export function spanQuery(filters: SpanFilters): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value === undefined || value === "") continue;
    params.set(key, String(value));
  }
  return params.toString();
}

export function useTrace(messageId: string | undefined) {
  return useQuery({
    queryKey: ["admin-trace", messageId],
    queryFn: () => apiJson<MessageTrace>(`/api/v1/admin/messages/${messageId}/spans`),
    enabled: Boolean(messageId),
  });
}

export function useSpanLogs(filters: SpanFilters) {
  return useQuery({
    queryKey: ["admin-spans", filters],
    queryFn: () => apiJson<SpanLogPage>(`/api/v1/admin/spans?${spanQuery(filters)}`),
  });
}

/** 走鉴权 fetch 拉 CSV 流，转 blob 后经临时 <a> 触发下载，用毕回收 objectURL */
export async function downloadSpansCsv(filters: Record<string, string | undefined>) {
  const res = await apiFetch(`/api/v1/admin/spans/export.csv?${spanQuery(filters)}`);
  if (!res.ok) throw new Error(`导出失败（HTTP ${res.status}）`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  try {
    const link = document.createElement("a");
    link.href = url;
    link.download = "spans.csv";
    document.body.appendChild(link);
    link.click();
    link.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}
