import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";
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
  lastPath: "",
  lastBody: null as unknown,
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
    path: string,
    body: unknown,
    onEvent: (e: { event: string; data: unknown }) => void,
  ) => {
    mockState.lastPath = path;
    mockState.lastBody = body;
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

function renderAt(sessionId: string, withSwitcher = false) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/sessions/${sessionId}`]}>
        <Routes>
          <Route
            path="/sessions/:sessionId"
            element={
              withSwitcher ? (
                <>
                  <ChatView />
                  <SessionSwitcher />
                </>
              ) : (
                <ChatView />
              )
            }
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** 模拟侧栏客户端跳转：ChatView 复用同一组件实例，仅 sessionId 变化 */
function SessionSwitcher() {
  const navigate = useNavigate();
  return (
    <button type="button" onClick={() => navigate("/sessions/s2")}>
      切换会话
    </button>
  );
}

beforeEach(() => {
  mockState.messages = [];
  mockState.agents = [];
  mockState.session = { id: "s1", agent_id: "a1" };
  mockState.lastPath = "";
  mockState.lastBody = null;
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
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

test("图片先上传再随消息发送，用户消息附件经鉴权 blob 渲染", async () => {
  mockState.messages = [
    {
      id: "u1",
      role: "user",
      blocks: [{ type: "text", content: "历史图片" }],
      status: "done",
      rating: null,
      error: null,
      created_at: "2026-09-12T10:00:00Z",
      attachments: [{ id: "att9", original_name: "cat.png", kind: "image", size_bytes: 4 }],
    },
  ];
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    if (String(input).includes("/attachments")) {
      return new Response(
        JSON.stringify({ id: "att10", original_name: "dog.png", kind: "image", size_bytes: 4 }),
        { status: 201 },
      );
    }
    return new Response(new Blob(["img"]), { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  URL.createObjectURL = vi.fn(() => "blob:mock");
  URL.revokeObjectURL = vi.fn();

  renderAt("s1");
  // 历史用户消息的附件：<img> 不能带 Bearer，改为经 apiFetch 取 blob 后 objectURL
  expect(await screen.findByAltText("附件图片")).toHaveAttribute("src", "blob:mock");
  expect(fetchMock).toHaveBeenCalledWith("/api/v1/attachments/att9", expect.anything());

  // 选择图片：先 POST 上传，返回 id 后显示预览 chip
  await userEvent.upload(
    screen.getByLabelText("选择图片"),
    new File(["png"], "dog.png", { type: "image/png" }),
  );
  expect(await screen.findByAltText("图片预览")).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/v1/sessions/s1/attachments",
    expect.objectContaining({ method: "POST" }),
  );

  // 发送：body 携带 attachment_ids，发送后清空 chip
  await userEvent.type(screen.getByPlaceholderText("输入问题，Enter 发送"), "带图{Enter}");
  await waitFor(() =>
    expect(mockState.lastBody).toEqual({
      content: "带图",
      mentions: [],
      attachment_ids: ["att10"],
    }),
  );
  expect(mockState.lastPath).toBe("/api/v1/sessions/s1/messages");
  await waitFor(() => expect(screen.queryByAltText("图片预览")).not.toBeInTheDocument());
});

test("切换会话丢弃待发附件，不会把旧会话的 attachment_id 发到新会话", async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    if (String(input).includes("/attachments")) {
      return new Response(
        JSON.stringify({ id: "attA", original_name: "a.png", kind: "image", size_bytes: 4 }),
        { status: 201 },
      );
    }
    return new Response(new Blob(["img"]), { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  URL.createObjectURL = vi.fn(() => "blob:a");
  URL.revokeObjectURL = vi.fn();

  renderAt("s1", true);
  await userEvent.upload(
    screen.getByLabelText("选择图片"),
    new File(["png"], "a.png", { type: "image/png" }),
  );
  expect(await screen.findByAltText("图片预览")).toBeInTheDocument();

  // 切换会话：pending chip 必须消失且预览 URL 被释放
  await userEvent.click(screen.getByRole("button", { name: "切换会话" }));
  await waitFor(() => expect(screen.queryByAltText("图片预览")).not.toBeInTheDocument());
  expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:a");

  // 新会话发送：不得携带旧会话的附件 id
  await userEvent.type(screen.getByPlaceholderText("输入问题，Enter 发送"), "新会话{Enter}");
  await waitFor(() =>
    expect(mockState.lastBody).toEqual({
      content: "新会话",
      mentions: [],
      attachment_ids: [],
    }),
  );
  expect(mockState.lastPath).toBe("/api/v1/sessions/s2/messages");
});

test("切换会话清空输入框草稿", async () => {
  renderAt("s1", true);
  const input = () => screen.getByPlaceholderText("输入问题，Enter 发送") as HTMLInputElement;
  await userEvent.type(input(), "不该带到新会话");
  expect(input().value).toBe("不该带到新会话");
  await userEvent.click(screen.getByRole("button", { name: "切换会话" }));
  await waitFor(() => expect(input().value).toBe(""));
});
