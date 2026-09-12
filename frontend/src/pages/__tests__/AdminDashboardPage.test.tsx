import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, test, vi } from "vitest";

const mockSetOption = vi.fn();
vi.mock("echarts", () => ({
  init: () => ({ setOption: mockSetOption, resize: vi.fn(), dispose: vi.fn() }),
}));

const mockState = vi.hoisted(() => ({ overview: null as unknown, hours: 24 }));
vi.mock("@/api/admin", () => ({
  useMetricsOverview: (hours: number) => {
    mockState.hours = hours;
    return { data: mockState.overview, isLoading: false, error: null };
  },
}));

import AdminDashboardPage from "@/pages/AdminDashboardPage";

function overview(overrides: Record<string, unknown> = {}) {
  return {
    hours: 24,
    cards: {
      llm_calls: 3, errors: 1, error_rate: 33.3, p95_ms: 812, prompt_tokens: 100,
      completion_tokens: 50, gpu_ms: 2400, model_switches: 1, switch_ms: 1200,
      tool_calls: 2, tool_error_rate: 0, retrieval_calls: 1, retrieval_avg_ms: 220,
      http_requests: 9, http_error_rate: 0,
    },
    series: [
      { hour: "2026-09-12T10:00:00+00:00", llm_calls: 3, prompt_tokens: 100,
        completion_tokens: 50, p95_ms: 812, errors: 1 },
    ],
    agents: [{ agent_id: "a1", name: "代码专家", llm_calls: 3, tokens: 150 }],
    models: [{ model: "qwen2.5:7b", llm_calls: 3, tokens: 150 }],
    tools: [{ tool: "kb_search", calls: 2, errors: 0, avg_ms: 12 }],
    switches: [{ from_model: "qwen2.5:7b", to_model: "deepseek-r1:latest", count: 1, avg_ms: 1200 }],
    retrieval: { calls: 1, errors: 0, avg_ms: 220 },
    http: { requests: 9, errors: 0, error_rate: 0, avg_ms: 3.2, series: [] },
    vram: [{ ts: "2026-09-12T10:00:00+00:00", vram_mb: 6200 }],
    ...overrides,
  };
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AdminDashboardPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mockState.overview = overview();
  mockState.hours = 24;
  mockSetOption.mockClear();
});

test("渲染指标卡片与四张图表容器", async () => {
  renderPage();
  expect(await screen.findByTestId("card-llm_calls")).toHaveTextContent("3");
  expect(screen.getByTestId("card-p95_ms")).toBeInTheDocument();
  for (const label of ["请求与 Token 趋势", "智能体活跃排行", "Token 分布", "显存曲线"]) {
    expect(screen.getByRole("img", { name: label })).toBeInTheDocument();
  }
  expect(mockSetOption).toHaveBeenCalled();
});

test("切换时间范围重新取数", async () => {
  renderPage();
  await userEvent.click(await screen.findByRole("button", { name: "7 天" }));
  expect(mockState.hours).toBe(168);
});

test("无数据展示空态", async () => {
  const base = overview();
  mockState.overview = {
    ...base,
    series: [],
    agents: [],
    models: [],
    vram: [],
    cards: { ...base.cards, llm_calls: 0 },
  };
  renderPage();
  expect(await screen.findByText("暂无调用数据")).toBeInTheDocument();
});
