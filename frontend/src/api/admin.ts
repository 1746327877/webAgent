import { useQuery } from "@tanstack/react-query";
import { apiJson } from "@/lib/api";

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
