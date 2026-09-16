import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const mcp = vi.hoisted(() => ({
  servers: [] as unknown[],
  create: vi.fn(),
  probe: vi.fn(),
  test: vi.fn(),
  remove: vi.fn(),
}));

vi.mock("@/api/capabilities", () => ({
  useParserStatus: () => ({
    data: {
      enabled: true,
      api_url: "http://host.docker.internal:8001",
      backend: "pipeline",
      healthy: true,
      version: "3.4.5",
      latency_ms: 12,
      error: null,
    },
    isLoading: false,
    error: null,
  }),
  useSkills: () => ({
    data: [
      {
        slug: "kb_qa",
        name: "知识库问答",
        icon: "📚",
        summary: "基于绑定的知识库检索作答。",
        usage: "绑定知识库并勾选检索工具。",
        instructions: "回答前先检索知识库。",
        examples: ["并发怎么处理的？"],
        recommended_tools: ["kb_search"],
      },
    ],
    isLoading: false,
    error: null,
  }),
}));

vi.mock("@/api/agents", () => ({
  useTools: () => ({
    data: [
      {
        id: "t1",
        slug: "kb_search",
        name: "知识库检索",
        description: "在绑定的知识库中检索片段",
        category: "knowledge",
        is_system: true,
        input_schema: {
          properties: { query: { type: "string" }, top_k: { type: "integer" } },
          required: ["query"],
        },
      },
    ],
    isLoading: false,
    error: null,
  }),
}));

vi.mock("@/api/mcp", () => ({
  useMcpServers: () => ({ data: mcp.servers, isLoading: false, error: null }),
  useCreateMcpServer: () => ({ mutateAsync: mcp.create, isPending: false }),
  useUpdateMcpServer: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteMcpServer: () => ({ mutate: mcp.remove, isPending: false }),
  useTestMcpServer: () => ({
    mutateAsync: mcp.test,
    isPending: false,
    variables: undefined,
  }),
  useProbeMcpConfig: () => ({ mutateAsync: mcp.probe, isPending: false }),
}));

import CapabilitiesPage from "@/pages/CapabilitiesPage";
import Toaster from "@/components/ui/toaster";
import { useToastStore } from "@/stores/toast";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <CapabilitiesPage />
      <Toaster />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mcp.servers = [];
  mcp.create.mockReset().mockResolvedValue({ id: "m1" });
  mcp.remove.mockReset();
  mcp.test
    .mockReset()
    .mockResolvedValue({ ok: true, tools: [], error: null, latency_ms: 5 });
  mcp.probe
    .mockReset()
    .mockResolvedValue({
      ok: true,
      tools: [{ name: "web_search", description: "网页搜索" }],
      error: null,
      latency_ms: 42,
    });
  useToastStore.getState().clear();
});

afterEach(cleanup);

test("三个标签页可切换，分别展示 Skill / MCP / Tool", async () => {
  renderPage();

  // 默认 Skill
  expect(await screen.findByText("知识库问答")).toBeInTheDocument();
  expect(screen.getByText("基于绑定的知识库检索作答。")).toBeInTheDocument();
  expect(screen.getByText(/回答前先检索知识库/)).toBeInTheDocument();

  await userEvent.click(screen.getByRole("tab", { name: "Tool" }));
  expect(await screen.findByText("知识库检索")).toBeInTheDocument();
  expect(screen.getByText("kb_search")).toBeInTheDocument();
  expect(screen.getByText("必填")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("tab", { name: "MCP" }));
  expect(await screen.findByText(/还没有 MCP/)).toBeInTheDocument();
});

test("解析标签页展示 MinerU 服务状态", async () => {
  renderPage();
  await userEvent.click(screen.getByRole("tab", { name: "解析" }));
  expect(await screen.findByText("MinerU 文档解析")).toBeInTheDocument();
  expect(screen.getByText("服务正常")).toBeInTheDocument();
  expect(screen.getByText("pipeline")).toBeInTheDocument();
  expect(screen.getByText("v3.4.5")).toBeInTheDocument();
});

test("MCP 新建：客户端校验必填项", async () => {
  renderPage();
  await userEvent.click(screen.getByRole("tab", { name: "MCP" }));
  await userEvent.click(screen.getByRole("button", { name: "＋ 新建 MCP" }));

  await userEvent.click(screen.getByRole("button", { name: "测试连接" }));
  expect(await screen.findByText("请填写名称")).toBeInTheDocument();
  expect(mcp.probe).not.toHaveBeenCalled();
});

test("MCP 新建：测试连接展示工具，保存调用创建", async () => {
  renderPage();
  await userEvent.click(screen.getByRole("tab", { name: "MCP" }));
  await userEvent.click(screen.getByRole("button", { name: "＋ 新建 MCP" }));

  await userEvent.type(screen.getByLabelText("名称"), "百度搜索");
  await userEvent.type(screen.getByLabelText("URL"), "https://mcp.example.com/mcp");

  await userEvent.click(screen.getByRole("button", { name: "测试连接" }));
  expect(await screen.findByText(/连接成功/)).toBeInTheDocument();
  expect(screen.getByText("web_search")).toBeInTheDocument();
  expect(mcp.probe).toHaveBeenCalledWith({
    name: "百度搜索",
    transport: "http",
    url: "https://mcp.example.com/mcp",
    headers: {},
  });

  await userEvent.click(screen.getByRole("button", { name: "保存" }));
  await waitFor(() => expect(mcp.create).toHaveBeenCalledTimes(1));
  expect(mcp.create.mock.calls[0][0]).toMatchObject({
    name: "百度搜索",
    transport: "http",
    url: "https://mcp.example.com/mcp",
  });
});

test("MCP 新建：http 缺少 url 时提示", async () => {
  renderPage();
  await userEvent.click(screen.getByRole("tab", { name: "MCP" }));
  await userEvent.click(screen.getByRole("button", { name: "＋ 新建 MCP" }));

  await userEvent.type(screen.getByLabelText("名称"), "无地址");
  await userEvent.click(screen.getByRole("button", { name: "保存" }));
  expect(await screen.findByText("http 连接需要填写 url")).toBeInTheDocument();
  expect(mcp.create).not.toHaveBeenCalled();
});

test("已保存的 MCP 可测试连接并展示状态", async () => {
  mcp.servers = [
    {
      id: "m1",
      name: "百度搜索",
      transport: "http",
      url: "https://mcp.example.com/mcp",
      headers: {},
      command: null,
      args: [],
      env: {},
      enabled: true,
      status: "unknown",
      last_error: null,
      tools: [],
      last_checked_at: null,
      created_at: null,
      updated_at: null,
    },
  ];
  mcp.test.mockResolvedValue({
    ok: true,
    tools: [{ name: "web_search", description: "网页搜索" }],
    error: null,
    latency_ms: 18,
  });

  renderPage();
  await userEvent.click(screen.getByRole("tab", { name: "MCP" }));
  expect(await screen.findByText("百度搜索")).toBeInTheDocument();
  expect(screen.getByText("未测试")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "测试连接" }));
  await waitFor(() => expect(mcp.test).toHaveBeenCalledWith("m1"));
  expect(await screen.findByText(/连接成功/)).toBeInTheDocument();
});
