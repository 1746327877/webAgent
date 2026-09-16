import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";

const mocks = vi.hoisted(() => ({ saved: null as unknown }));

const SERVERS = [
  {
    id: "srv-1",
    name: "瑞星咖啡",
    transport: "http",
    url: "https://mcp.example.com/mcp",
    headers: {},
    command: null,
    args: [],
    env: {},
    enabled: true,
    status: "ok",
    last_error: null,
    tools: [
      { name: "queryShopList", description: "门店列表" },
      { name: "createOrder", description: "下单" },
    ],
    last_checked_at: null,
    created_at: null,
    updated_at: null,
  },
];

vi.mock("@/api/mcp", () => ({
  useMcpServers: () => ({ data: SERVERS, isLoading: false }),
}));

vi.mock("@/api/agents", () => ({
  useSetAgentMcpTools: () => ({
    mutateAsync: async (payload: unknown) => {
      mocks.saved = payload;
      return { tools: [] };
    },
    isPending: false,
  }),
}));

import McpBindings from "@/components/agents/McpBindings";

const AGENT = {
  id: "a1",
  name: "咖啡点单",
  emoji: "☕",
  description: null,
  tags: [],
  system_prompt: "",
  model_config: {},
  welcome_msg: null,
  examples: [],
  status: "draft",
  current_version: 0,
  variables: [],
  tool_slugs: [],
  skill_slugs: [],
  mcp_tools: [],
  kb_bindings: [],
  has_avatar: false,
  created_at: "t",
  updated_at: "t",
};

beforeEach(() => {
  mocks.saved = null;
});

test("父复选框勾选即全选该 server 的全部 tool", async () => {
  render(<McpBindings agent={AGENT} onNotice={vi.fn()} onError={vi.fn()} />);
  expect(screen.getByRole("checkbox", { name: /queryShopList/ })).not.toBeChecked();

  await userEvent.click(screen.getByRole("checkbox", { name: "全选 瑞星咖啡" }));

  expect(screen.getByRole("checkbox", { name: /queryShopList/ })).toBeChecked();
  expect(screen.getByRole("checkbox", { name: /createOrder/ })).toBeChecked();
  expect(screen.getByRole("checkbox", { name: "全选 瑞星咖啡" })).toBeChecked();
});

test("取消父复选框清空该 server", async () => {
  render(<McpBindings agent={AGENT} onNotice={vi.fn()} onError={vi.fn()} />);
  await userEvent.click(screen.getByRole("checkbox", { name: "全选 瑞星咖啡" }));
  await userEvent.click(screen.getByRole("checkbox", { name: "全选 瑞星咖啡" }));
  expect(screen.getByRole("checkbox", { name: /queryShopList/ })).not.toBeChecked();
});

test("部分勾选时父复选框为 indeterminate", async () => {
  render(<McpBindings agent={AGENT} onNotice={vi.fn()} onError={vi.fn()} />);
  await userEvent.click(screen.getByRole("checkbox", { name: /createOrder/ }));
  const parent = screen.getByRole("checkbox", { name: "全选 瑞星咖啡" }) as HTMLInputElement;
  expect(parent.indeterminate).toBe(true);
  expect(parent).not.toBeChecked();
});
