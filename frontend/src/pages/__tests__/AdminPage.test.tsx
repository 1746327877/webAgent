import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { expect, test, vi } from "vitest";

vi.mock("@/pages/AdminDashboardPage", () => ({
  default: () => <div>概览内容</div>,
}));

const SESSIONS = [
  {
    id: "s1",
    title: "并发问题排查",
    agent_id: "a1",
    pinned: false,
    archived: false,
    last_message_at: "2026-09-16T10:00:00Z",
    created_at: "t",
    updated_at: "t",
  },
  {
    id: "s2",
    title: "咖啡点单记录",
    agent_id: "a2",
    pinned: true,
    archived: false,
    last_message_at: "2026-09-16T11:00:00Z",
    created_at: "t",
    updated_at: "t",
  },
];

vi.mock("@/api/sessions", () => ({
  useSessions: () => ({
    data: { pages: [{ items: SESSIONS, total: SESSIONS.length }] },
    isLoading: false,
    error: null,
  }),
  useMessages: () => ({ data: [], isLoading: false }),
}));

vi.mock("@/api/agents", () => ({
  useAgents: () => ({
    data: [
      { id: "a1", name: "代码专家", emoji: "💻" },
      { id: "a2", name: "咖啡点单", emoji: "☕" },
    ],
  }),
}));

vi.mock("@/api/admin", () => ({
  useTrace: () => ({
    data: { trace_id: "m1", message: { status: "done" }, spans: [] },
    isLoading: false,
    error: null,
  }),
  useSpanLogs: () => ({ data: { items: [], total: 0 } }),
  downloadSpansCsv: async () => {},
}));

import AdminPage from "@/pages/AdminPage";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/admin"]}>
        <AdminPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test("默认概览，只有概览与会话记录两个子标签", () => {
  renderPage();
  expect(screen.getByRole("tab", { name: "概览" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("tab", { name: "会话记录" })).toBeInTheDocument();
  expect(screen.queryByRole("tab", { name: "调用链" })).not.toBeInTheDocument();
  expect(screen.getByText("概览内容")).toBeInTheDocument();
});

test("会话记录：列出会话并内嵌调用链", async () => {
  renderPage();
  await userEvent.click(screen.getByRole("tab", { name: "会话记录" }));

  expect(await screen.findByText("并发问题排查")).toBeInTheDocument();
  expect(screen.getByText("咖啡点单记录")).toBeInTheDocument();
  expect(screen.getByLabelText("按智能体筛选")).toBeInTheDocument();

  // 默认选中第一条并在右侧渲染调用链
  expect(screen.getByText("🔍 会话调用链")).toBeInTheDocument();

  await userEvent.click(screen.getByText("咖啡点单记录"));
  expect(screen.getByText("🔍 会话调用链")).toBeInTheDocument();
});

test("会话记录：按智能体筛选只显示该智能体的会话", async () => {
  renderPage();
  await userEvent.click(screen.getByRole("tab", { name: "会话记录" }));
  await screen.findByText("并发问题排查");

  await userEvent.selectOptions(screen.getByLabelText("按智能体筛选"), "a2");
  expect(screen.queryByText("并发问题排查")).not.toBeInTheDocument();
  expect(screen.getByText("咖啡点单记录")).toBeInTheDocument();
  expect(screen.getByText("共 1 个会话")).toBeInTheDocument();
});
