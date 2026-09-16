import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, expect, test, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  create: vi.fn(),
  setTools: vi.fn(),
  setSkills: vi.fn(),
  setMcp: vi.fn(),
  uploadAvatar: vi.fn(),
}));

vi.mock("@/components/ui/slider", () => ({ Slider: () => null }));

vi.mock("@/api/kbs", () => ({ useKbs: () => ({ data: [] }) }));

vi.mock("@/api/capabilities", () => ({
  useSkills: () => ({
    data: [
      {
        slug: "kb_qa",
        name: "知识库问答",
        icon: "📚",
        summary: "检索作答",
        usage: "绑定知识库",
        instructions: "先检索",
        examples: [],
        recommended_tools: [],
      },
    ],
    isLoading: false,
  }),
}));

vi.mock("@/api/mcp", () => ({
  useMcpServers: () => ({
    data: [
      {
        id: "srv-1",
        name: "瑞星咖啡",
        transport: "http",
        status: "ok",
        tools: [{ name: "queryShopList", description: "门店列表" }],
      },
    ],
    isLoading: false,
  }),
}));

vi.mock("@/api/agents", () => ({
  useAgent: () => ({ data: undefined, isLoading: false, error: null }),
  useModels: () => ({ data: [] }),
  useTools: () => ({
    data: [
      {
        id: "t1",
        slug: "time_now",
        name: "当前时间",
        description: "现在几点",
        category: "system",
        is_system: true,
      },
    ],
  }),
  useCreateAgent: () => ({ mutateAsync: mocks.create, isPending: false }),
  useUpdateAgent: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteAgent: () => ({ mutateAsync: vi.fn(), isPending: false }),
  usePublishAgent: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useSetAgentTools: () => ({ mutateAsync: mocks.setTools, isPending: false }),
  useSetAgentSkills: () => ({ mutateAsync: mocks.setSkills, isPending: false }),
  useSetAgentMcpTools: () => ({ mutateAsync: mocks.setMcp, isPending: false }),
  useUploadAgentAvatar: () => ({ mutateAsync: mocks.uploadAvatar, isPending: false }),
  useDeleteAgentAvatar: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useAgentVersions: () => ({ data: [], isLoading: false, error: null }),
  useRollbackAgent: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

import AgentEditorPage from "@/pages/AgentEditorPage";

function renderNew() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/agents/new"]}>
        <Routes>
          <Route path="/agents/new" element={<AgentEditorPage />} />
          <Route path="/agents/:agentId" element={<div>detail</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mocks.create.mockReset().mockResolvedValue({ id: "new-1", name: "咖啡点单" });
  mocks.setTools.mockReset().mockResolvedValue({ slugs: [] });
  mocks.setSkills.mockReset().mockResolvedValue({ slugs: [] });
  mocks.setMcp.mockReset().mockResolvedValue({ tools: [] });
  mocks.uploadAvatar.mockReset().mockResolvedValue({});
});

test("新建智能体也有「扩展能力」标签，可先选 Skill/MCP/Tool", async () => {
  renderNew();
  expect(screen.getByRole("tab", { name: "扩展能力" })).toBeInTheDocument();

  await userEvent.click(screen.getByRole("tab", { name: "扩展能力" }));
  // 默认 Skill 子标签
  expect(await screen.findByText(/知识库问答/)).toBeInTheDocument();

  await userEvent.click(screen.getByRole("tab", { name: "MCP" }));
  expect(await screen.findByText("瑞星咖啡")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("tab", { name: "Tool" }));
  expect(await screen.findByText("当前时间")).toBeInTheDocument();
});

test("创建成功后自动写入所选的扩展能力", async () => {
  renderNew();
  await userEvent.click(screen.getByRole("tab", { name: "扩展能力" }));

  // Skill：全选
  await userEvent.click(await screen.findByRole("checkbox", { name: "全选 Skill" }));
  // MCP：整台 server 全选
  await userEvent.click(screen.getByRole("tab", { name: "MCP" }));
  await userEvent.click(await screen.findByRole("checkbox", { name: "全选 瑞星咖啡" }));
  // Tool：勾选「当前时间」
  await userEvent.click(screen.getByRole("tab", { name: "Tool" }));
  await userEvent.click(await screen.findByLabelText("当前时间"));

  // 回到基础信息填名字并保存
  await userEvent.click(screen.getByRole("tab", { name: "基础信息" }));
  await userEvent.type(screen.getByLabelText("名称"), "咖啡点单");
  await userEvent.click(screen.getByRole("button", { name: "保存" }));

  await waitFor(() => expect(mocks.create).toHaveBeenCalledTimes(1));
  await waitFor(() => expect(mocks.setTools).toHaveBeenCalledWith({ id: "new-1", slugs: ["time_now"] }));
  expect(mocks.setSkills).toHaveBeenCalledWith({ id: "new-1", slugs: ["kb_qa"] });
  expect(mocks.setMcp).toHaveBeenCalledWith({
    id: "new-1",
    tools: [{ mcp_server_id: "srv-1", tool_name: "queryShopList" }],
  });
});
