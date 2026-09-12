import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { ReactNode } from "react";
import type { MessageItemData } from "@/api/sessions";

// jsdom 无 ResizeObserver/布局，Virtuoso 不会渲染任何行；测试里退化为全量渲染
vi.mock("react-virtuoso", () => ({
  Virtuoso: ({
    data,
    itemContent,
  }: {
    data: MessageItemData[];
    itemContent: (index: number, item: MessageItemData) => ReactNode;
  }) => (
    <>
      {data.map((item, index) => (
        <div key={index}>{itemContent(index, item)}</div>
      ))}
    </>
  ),
}));

// 各用例可按需覆盖的 mock 数据；beforeEach 恢复默认，避免用例间串扰
const mockState = vi.hoisted(() => ({
  messages: [] as MessageItemData[],
  agents: [] as { id: string; name: string; emoji: string }[],
  session: { id: "s1", agent_id: "a1" } as { id: string; agent_id: string | null },
}));

vi.mock("@/api/sessions", () => ({
  useCreateSession: () => ({ mutateAsync: vi.fn() }),
  useMessages: () => ({ data: mockState.messages }),
  useSession: () => ({ data: mockState.session }),
}));

vi.mock("@/api/agents", () => ({
  useAgent: () => ({
    data: {
      id: "a1",
      name: "代码专家",
      emoji: "💻",
      welcome_msg: "贴代码给我",
      examples: ["帮我 review 这段"],
    },
  }),
  useAgents: () => ({ data: mockState.agents }),
}));

// 流式事件按序同步派发后挂起，便于断言叠加层渲染（结束后会被 clearActive 清掉）
vi.mock("@/lib/stream", () => ({
  streamRequest: async (
    _path: string,
    _body: unknown,
    onEvent: (e: { event: string; data: unknown }) => void,
  ) => {
    onEvent({ event: "message_start", data: { message_id: "m1" } });
    onEvent({
      event: "citation",
      data: {
        message_id: "m1",
        ref: 1,
        chunk_id: "k1",
        source: "rag.md",
        page: 3,
        score: 0.9,
        snippet: "混合检索片段",
      },
    });
    onEvent({
      event: "tool_call",
      data: { message_id: "m1", id: "c1", name: "kb_search", args: { query: "x" } },
    });
    onEvent({
      event: "tool_result",
      data: { message_id: "m1", id: "c1", status: "ok", elapsed_ms: 12, preview: "命中" },
    });
    onEvent({ event: "token", data: { message_id: "m1", delta: "答案[1]" } });
    await new Promise(() => {});
  },
}));

import ChatView from "@/components/chat/ChatView";
import { useChatStreamStore } from "@/stores/chatStream";

function renderAt(sessionId: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/sessions/${sessionId}`]}>
        <Routes>
          <Route path="/sessions/:sessionId" element={<ChatView />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mockState.messages = [];
  mockState.agents = [];
  mockState.session = { id: "s1", agent_id: "a1" };
});

afterEach(() => {
  cleanup();
  useChatStreamStore.getState().clear();
});

test("其他会话的流式叠加层不会泄漏到当前会话", () => {
  useChatStreamStore.setState({
    active: {
      id: "m-other",
      sessionId: "other",
      content: "泄漏内容",
      thinking: "",
      citations: [],
      toolEvents: [],
    },
    error: null,
  });
  renderAt("current");
  expect(screen.queryByText("泄漏内容")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "停止" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "发送" })).toBeInTheDocument();
});

test("当前会话的流式叠加层正常显示且可停止", () => {
  useChatStreamStore.setState({
    active: {
      id: "m-current",
      sessionId: "current",
      content: "进行中内容",
      thinking: "",
      citations: [],
      toolEvents: [],
    },
    error: null,
  });
  renderAt("current");
  expect(screen.getByText("进行中内容")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "停止" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "发送" })).not.toBeInTheDocument();
});

test("当前会话的错误可见", () => {
  useChatStreamStore.setState({
    active: null,
    error: { sessionId: "current", message: "本会话错误" },
  });
  renderAt("current");
  expect(screen.getByText("出错：本会话错误")).toBeInTheDocument();
});

test("其他会话的错误不显示", () => {
  useChatStreamStore.setState({
    active: null,
    error: { sessionId: "other", message: "其他会话错误" },
  });
  renderAt("current");
  expect(screen.queryByText("出错：其他会话错误")).not.toBeInTheDocument();
});

test("无会话时显示创建失败错误", () => {
  useChatStreamStore.setState({
    active: null,
    error: { sessionId: null, message: "创建失败" },
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<ChatView />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  expect(screen.getByText("出错：创建失败")).toBeInTheDocument();
});

test("空会话展示智能体欢迎语与示例", async () => {
  renderAt("s1");
  expect(await screen.findByText("贴代码给我")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "帮我 review 这段" })).toBeInTheDocument();
});

test("citation/tool 事件流式出现，点击角标打开依据抽屉", async () => {
  renderAt("s1");
  await userEvent.type(screen.getByPlaceholderText("输入问题，Enter 发送"), "并发要点{Enter}");
  // citation 事件流式渲染「回答依据」
  expect(await screen.findByText(/回答依据/)).toBeInTheDocument();
  expect(screen.getByText(/rag\.md/)).toBeInTheDocument();
  // tool_call/tool_result 实时出现，不再等待 invalidate
  expect(screen.getByText(/调用工具/)).toBeInTheDocument();
  expect(screen.getAllByText(/kb_search/).length).toBeGreaterThanOrEqual(2);
  expect(screen.getByText(/12ms/)).toBeInTheDocument();
  // [1] 被 linkify 为可点击角标，点击前抽屉未展示 snippet
  const link = screen.getByRole("link", { name: "1" });
  expect(link).toHaveAttribute("href", "#cite-1");
  expect(screen.queryByText("混合检索片段")).not.toBeInTheDocument();
  await userEvent.click(link);
  expect(await screen.findByText("混合检索片段")).toBeInTheDocument();
  expect(screen.getByText(/第 3 页/)).toBeInTheDocument();
});

test("助手消息显示智能体徽标与接力标签", async () => {
  mockState.messages = [
    {
      id: "m1",
      role: "assistant",
      blocks: [{ type: "text", content: "主智能体回答" }],
      status: "done",
      rating: null,
      error: null,
      created_at: "2026-09-12T10:00:00Z",
      agent_id: "a1",
    },
    {
      id: "m2",
      role: "assistant",
      blocks: [{ type: "text", content: "接力回答" }],
      status: "done",
      rating: null,
      error: null,
      created_at: "2026-09-12T10:00:01Z",
      agent_id: "a2",
    },
  ];
  mockState.agents = [
    { id: "a1", name: "甲", emoji: "🅰" },
    { id: "a2", name: "乙", emoji: "🅱" },
  ];
  renderAt("s1");
  expect(await screen.findByText("甲")).toBeInTheDocument();
  expect(await screen.findByText(/接力.*乙/)).toBeInTheDocument();
});
