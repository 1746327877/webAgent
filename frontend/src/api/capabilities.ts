import { useQuery } from "@tanstack/react-query";
import { apiJson } from "@/lib/api";

/** 与后端 app/ai/skills.py 的 SkillDef 字段一致 */
export interface SkillInfo {
  slug: string;
  name: string;
  icon: string;
  summary: string;
  usage: string;
  instructions: string;
  examples: string[];
  recommended_tools: string[];
}

export function useSkills() {
  return useQuery({
    queryKey: ["capabilities", "skills"],
    queryFn: () => apiJson<SkillInfo[]>("/api/v1/capabilities/skills"),
  });
}

/** MinerU 解析服务状态（后端 app/api/v1/capabilities.py 的 /parser） */
export interface ParserStatus {
  enabled: boolean;
  api_url: string | null;
  backend: string;
  healthy: boolean;
  version: string | null;
  latency_ms: number | null;
  error: string | null;
}

export function useParserStatus() {
  return useQuery({
    queryKey: ["capabilities", "parser"],
    queryFn: () => apiJson<ParserStatus>("/api/v1/capabilities/parser"),
    refetchInterval: 30000,
  });
}

/** 联网搜索 MCP 状态（后端 app/api/v1/capabilities.py 的 /web-search） */
export interface WebSearchStatus {
  enabled: boolean;
  url: string | null;
  healthy: boolean;
  tools: string[];
  latency_ms: number | null;
  error: string | null;
}

export function useWebSearchStatus() {
  return useQuery({
    queryKey: ["capabilities", "web-search"],
    queryFn: () => apiJson<WebSearchStatus>("/api/v1/capabilities/web-search"),
    refetchInterval: 30000,
  });
}
