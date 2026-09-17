import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, expect, test, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  mutateAsync: vi.fn(),
  agents: [] as unknown[],
}));

vi.mock("@/api/agents", () => ({
  useAgents: () => ({ data: mocks.agents, isLoading: false, error: null }),
}));

vi.mock("@/api/sessions", () => ({
  useCreateSession: () => ({ mutateAsync: mocks.mutateAsync }),
}));

import AgentsPage from "@/pages/AgentsPage";
import { useToastStore } from "@/stores/toast";

function makeAgent(id: string, name: string) {
  return {
    id,
    name,
    has_avatar: false,
    updated_at: "2026-09-17T00:00:00Z",
    description: "描述",
    tags: [],
    status: "published",
    current_version: 1,
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/agents"]}>
      <Routes>
        <Route path="/agents" element={<AgentsPage />} />
        <Route path="/sessions/:id" element={<p>会话页</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mocks.mutateAsync.mockReset();
  useToastStore.getState().clear();
});

test("点击「进入对话」为该智能体新建会话并跳转", async () => {
  mocks.agents = [makeAgent("a1", "会议专家")];
  mocks.mutateAsync.mockResolvedValue({ id: "s-new" });
  renderPage();

  await userEvent.click(screen.getByRole("button", { name: "和「会议专家」对话" }));

  expect(mocks.mutateAsync).toHaveBeenCalledWith("a1");
  expect(await screen.findByText("会话页")).toBeInTheDocument();
});

test("卡片本身仍然指向编辑页", () => {
  mocks.agents = [makeAgent("a1", "会议专家")];
  renderPage();

  // 「进入对话」按钮放在 Link 之外，链接语义保持"整卡进编辑"
  expect(screen.getByRole("link")).toHaveAttribute("href", "/agents/a1");
});

test("创建会话失败时提示且不跳转", async () => {
  mocks.agents = [makeAgent("a1", "会议专家")];
  mocks.mutateAsync.mockRejectedValue(new Error("创建会话失败"));
  renderPage();

  await userEvent.click(screen.getByRole("button", { name: "和「会议专家」对话" }));

  expect(useToastStore.getState().toasts.map((t) => t.message)).toContain("创建会话失败");
  expect(screen.queryByText("会话页")).not.toBeInTheDocument();
});
