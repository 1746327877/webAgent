import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, test, vi } from "vitest";

const mockSetOption = vi.fn();
const mockDispose = vi.fn();
vi.mock("echarts", () => ({
  init: () => ({ setOption: mockSetOption, resize: vi.fn(), dispose: mockDispose }),
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
  mockDispose.mockClear();
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

type CapturedOption = {
  series: Array<Record<string, unknown>>;
  legend?: { top?: unknown };
  xAxis?: { data?: unknown[] } | Array<{ data?: unknown[] }>;
  yAxis?: { name?: string; data?: unknown[] } | Array<{ name?: string; data?: unknown[] }>;
};

function capturedOptions(): CapturedOption[] {
  return mockSetOption.mock.calls.map(([option]) => option as CapturedOption);
}

function findOption(
  options: CapturedOption[],
  predicate: (option: CapturedOption) => boolean,
): CapturedOption {
  const found = options.find(predicate);
  expect(found).toBeDefined();
  return found as CapturedOption;
}

test("图表 option 按接口数据映射（趋势双轴 / 智能体柱状 / 显存折线）", async () => {
  renderPage();
  await screen.findByTestId("card-llm_calls");
  const options = capturedOptions();
  expect(options).toHaveLength(4);

  const trend = findOption(options, (o) => o.series.length === 3);
  expect(trend.series.map((s) => s.name)).toEqual(["LLM 调用", "Prompt Token", "Completion Token"]);
  expect(trend.series.map((s) => s.yAxisIndex)).toEqual([undefined, 1, 1]);
  expect(trend.series.map((s) => s.data)).toEqual([[3], [100], [50]]);
  expect(trend.yAxis).toEqual([
    { type: "value", name: "调用" },
    { type: "value", name: "Token" },
  ]);
  // ECharts 6 图例默认置底会压住 x 轴，回退为置顶
  expect(trend.legend?.top).toBe(0);

  const bar = findOption(options, (o) => o.series[0]?.type === "bar");
  expect((bar.yAxis as { data: unknown[] }).data).toEqual(["代码专家"]);
  expect(bar.series[0].data).toEqual([150]);

  const vram = findOption(
    options,
    (o) =>
      o.series[0]?.type === "line" &&
      !Array.isArray(o.yAxis) &&
      (o.yAxis as { name?: string })?.name === "MB",
  );
  expect((vram.xAxis as { data: unknown[] }).data).toEqual(["09-12 10:00"]);
  expect(vram.series[0].data).toEqual([6200]);
});

test("卸载时销毁全部 ECharts 实例", async () => {
  const { unmount } = renderPage();
  await screen.findByTestId("card-llm_calls");
  unmount();
  expect(mockDispose).toHaveBeenCalledTimes(4);
});
