import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { expect, test, vi } from "vitest";

// 可变 mock：模拟回滚后 useAgent 重新拉取到 updated_at 变化的新数据
const mockAgent = vi.hoisted(() => ({
  current: {
    id: "a1",
    name: "A",
    emoji: "🤖",
    description: null,
    tags: [] as string[],
    system_prompt: "",
    model_config: {},
    welcome_msg: null,
    examples: [] as string[],
    status: "draft",
    current_version: 1,
    variables: [] as string[],
    tool_slugs: [] as string[],
    created_at: "t0",
    updated_at: "t1",
  },
}));

vi.mock("@/components/ui/slider", () => ({ Slider: () => null }));

vi.mock("@/api/agents", () => ({
  useAgent: () => ({ data: mockAgent.current, isLoading: false, error: null }),
  useModels: () => ({ data: [] }),
  useTools: () => ({ data: [] }),
  useCreateAgent: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateAgent: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteAgent: () => ({ mutateAsync: vi.fn(), isPending: false }),
  usePublishAgent: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useSetAgentTools: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useAgentVersions: () => ({ data: [], isLoading: false, error: null }),
  useRollbackAgent: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

import AgentEditorPage from "@/pages/AgentEditorPage";

function renderEditor() {
  return render(
    <MemoryRouter initialEntries={["/agents/a1"]}>
      <Routes>
        <Route path="/agents/:agentId" element={<AgentEditorPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

test("回滚后 updated_at 变化触发表单重挂载并展示服务端新值", () => {
  const view = renderEditor();
  expect(screen.getByLabelText("名称")).toHaveValue("A");

  mockAgent.current.name = "B";
  mockAgent.current.updated_at = "t2";
  view.rerender(
    <MemoryRouter initialEntries={["/agents/a1"]}>
      <Routes>
        <Route path="/agents/:agentId" element={<AgentEditorPage />} />
      </Routes>
    </MemoryRouter>,
  );

  expect(screen.getByLabelText("名称")).toHaveValue("B");
});
