import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
    skill_slugs: [] as string[],
    mcp_tools: [] as { mcp_server_id: string; tool_name: string }[],
    kb_bindings: [] as { kb_id: string; name: string; top_k: number; score_threshold: number }[],
    created_at: "t0",
    updated_at: "t1",
  },
}));

vi.mock("@/components/ui/slider", () => ({ Slider: () => null }));

vi.mock("@/api/kbs", () => ({
  useKbs: () => ({ data: [] }),
}));

vi.mock("@/api/capabilities", () => ({
  useSkills: () => ({
    data: [
      {
        slug: "kb_qa",
        name: "知识库问答",
        icon: "📚",
        summary: "基于绑定的知识库检索作答。",
        usage: "绑定知识库。",
        instructions: "先检索。",
        examples: [],
        recommended_tools: ["kb_search"],
      },
    ],
    isLoading: false,
  }),
}));

vi.mock("@/api/mcp", () => ({
  useMcpServers: () => ({
    data: [
      {
        id: "m1",
        name: "Baidu Search",
        transport: "http",
        url: "https://x/mcp",
        headers: {},
        command: null,
        args: [],
        env: {},
        enabled: true,
        status: "ok",
        last_error: null,
        tools: [{ name: "web_search", description: "网页搜索" }],
        last_checked_at: null,
        created_at: null,
        updated_at: null,
      },
    ],
    isLoading: false,
  }),
}));

vi.mock("@/api/agents", () => ({
  useAgent: () => ({ data: mockAgent.current, isLoading: false, error: null }),
  useModels: () => ({ data: [] }),
  useTools: () => ({ data: [] }),
  useCreateAgent: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateAgent: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteAgent: () => ({ mutateAsync: vi.fn(), isPending: false }),
  usePublishAgent: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useSetAgentTools: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useSetAgentSkills: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useSetAgentMcpTools: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useSetAgentKbs: () => ({ mutateAsync: vi.fn(), isPending: false }),
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

test("扩展能力标签页：子标签切换 Skill / MCP / Tool，MCP 父级全选", async () => {
  renderEditor();
  const capabilitiesTab = screen.getByRole("tab", { name: "扩展能力" });
  await userEvent.click(capabilitiesTab);
  expect(capabilitiesTab).toHaveAttribute("aria-selected", "true");

  // 默认 Skill 子标签
  expect(screen.getByText(/知识库问答/)).toBeInTheDocument();

  // 切到 MCP 子标签
  await userEvent.click(screen.getByRole("tab", { name: "MCP" }));
  expect(screen.getByText("Baidu Search")).toBeInTheDocument();
  expect(screen.getByText("web_search")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "保存 MCP 绑定" })).toBeInTheDocument();

  // 父级全选：勾选 server 即全选其下 tool
  await userEvent.click(screen.getByRole("checkbox", { name: "全选 Baidu Search" }));
  expect(screen.getByRole("checkbox", { name: /web_search/ })).toBeChecked();

  // 切到 Tool 子标签
  await userEvent.click(screen.getByRole("tab", { name: "Tool" }));
  expect(screen.getByRole("button", { name: "保存工具绑定" })).toBeInTheDocument();
});
