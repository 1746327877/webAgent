import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const mockState = vi.hoisted(() => ({
  logs: { items: [] as unknown[], total: 0 },
  logFilters: null as unknown,
  exported: null as unknown,
  ackCalls: [] as string[],
}));

const LLM_SPAN = {
  id: "sp-llm", parent_span_id: null, type: "llm", name: "qwen2.5:7b", status: "ok",
  model: "qwen2.5:7b", error: null, prompt_tokens: 7, completion_tokens: 3, duration_ms: 800,
  started_at: "2026-09-12T10:00:00+00:00", ended_at: "2026-09-12T10:00:00.8+00:00",
  session_id: "s1", message_id: "m1", agent_id: null,
  input: { messages: [] }, output: { text: "答案", first_token_ms: 120 },
};
const TOOL_SPAN = {
  ...LLM_SPAN, id: "sp-tool", parent_span_id: "sp-llm", type: "tool", name: "kb_search",
  status: "ok", duration_ms: 120, input: { args: { query: "线程池" } }, output: { result: "命中" },
  started_at: "2026-09-12T10:00:00.2+00:00", ended_at: "2026-09-12T10:00:00.32+00:00",
};

vi.mock("@/api/admin", () => ({
  useTrace: () => ({ data: { trace_id: "m1", message: { status: "done" }, spans: [LLM_SPAN, TOOL_SPAN] } }),
  useSpanLogs: (filters: unknown) => {
    mockState.logFilters = filters;
    return { data: mockState.logs };
  },
  downloadSpansCsv: async (filters: unknown) => {
    mockState.exported = filters;
  },
}));

vi.mock("@/api/sessions", () => ({
  useMessages: () => ({
    data: [
      {
        id: "m1", role: "assistant", blocks: [{ type: "text", content: "答案" }],
        status: "done", rating: null, error: null, created_at: "2026-09-12T10:00:00Z",
      },
    ],
  }),
}));

import AdminTracePage from "@/pages/AdminTracePage";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/admin/sessions/s1"]}>
        <Routes>
          <Route path="/admin/sessions/:sessionId" element={<AdminTracePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mockState.logs = {
    total: 1,
    items: [TOOL_SPAN],
  };
  mockState.exported = null;
  mockState.logFilters = null;
});

afterEach(() => {
  vi.unstubAllGlobals();
});

test("渲染 waterfall 条与工具日志表", async () => {
  renderPage();
  expect(await screen.findByLabelText("span-llm")).toBeInTheDocument();
  expect(screen.getByLabelText("span-tool")).toBeInTheDocument();
  expect(screen.getByText("kb_search")).toBeInTheDocument();
});

test("左上角「←」可直接返回该会话的对话", async () => {
  renderPage();
  const back = await screen.findByRole("link", { name: "返回对话" });
  expect(back).toHaveAttribute("href", "/sessions/s1");
});

test("点击 span 打开 JSON 抽屉", async () => {
  renderPage();
  await userEvent.click(await screen.findByLabelText("span-tool"));
  expect(await screen.findByText(/输入/)).toBeInTheDocument();
  expect(screen.getByText(/线程池/)).toBeInTheDocument();
});

test("状态筛选透传查询并导出 CSV", async () => {
  renderPage();
  await userEvent.selectOptions(await screen.findByLabelText("状态筛选"), "error");
  await waitFor(() => expect(mockState.logFilters).toMatchObject({ status: "error" }));
  await userEvent.click(screen.getByRole("button", { name: "导出 CSV" }));
  await waitFor(() => expect(mockState.exported).toMatchObject({ status: "error" }));
});

test("日志总数超过单页时展示总数与显示范围，并按上限取数", async () => {
  mockState.logs = { total: 120, items: [TOOL_SPAN] };
  renderPage();
  expect(await screen.findByText("共 120 条，显示前 1 条")).toBeInTheDocument();
  expect(mockState.logFilters).toMatchObject({ session_id: "s1", limit: 200 });
});

test("日志为空时展示空态且不显示范围提示", async () => {
  mockState.logs = { total: 0, items: [] };
  renderPage();
  expect(await screen.findByText("暂无日志")).toBeInTheDocument();
  expect(screen.queryByText(/显示前/)).not.toBeInTheDocument();
});
