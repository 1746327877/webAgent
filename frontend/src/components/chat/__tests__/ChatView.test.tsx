import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
  models: [] as { name: string; size_mb: number | null; capabilities?: string[] }[],
  session: { id: "s1", agent_id: "a1", title: "并发问题排查" } as {
    id: string;
    agent_id: string | null;
    title: string;
  },
  lastPath: "",
  lastBody: null as unknown,
  tokens: [] as string[],
  createCalls: 0,
}));

vi.mock("@/api/sessions", () => ({
  useCreateSession: () => ({
    mutateAsync: vi.fn(async () => {
      mockState.createCalls += 1;
      return { id: "new-1" };
    }),
  }),
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
  useModels: () => ({ data: mockState.models }),
  // ChatView 用它把 AgentItem 收敛成"头像 + 名字"的精简展示对象
  toAgentBadge: (agent: {
    id: string;
    name: string;
    has_avatar?: boolean;
    updated_at?: string;
  }) => ({
    id: agent.id,
    name: agent.name,
    has_avatar: agent.has_avatar,
    updated_at: agent.updated_at,
  }),
}));

// 联网搜索按钮的可用性来自能力探测接口；这里固定为"已配置且健康"
vi.mock("@/api/capabilities", () => ({
  useWebSearchStatus: () => ({
    data: { enabled: true, healthy: true, url: "http://ws/mcp", tools: ["search"], error: null },
  }),
}));

// 产物：ChatView 头部有「导出纪要 / 产物」按钮，避免测试里发真实请求
vi.mock("@/api/artifacts", () => ({
  useArtifacts: () => ({ data: [], isLoading: false }),
  useExportMarkdown: () => ({ mutateAsync: vi.fn(), isPending: false }),
  artifactFileUrl: (id: string) => `/api/v1/artifacts/${id}`,
  downloadArtifact: vi.fn(),
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
        headings: ["第3章", "3.1 核心参数"],
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
    for (const delta of mockState.tokens) {
      onEvent({ event: "token", data: { message_id: "m1", delta } });
    }
    await new Promise(() => {});
  },
}));

import ChatView from "@/components/chat/ChatView";
import { useChatStreamStore } from "@/stores/chatStream";
import { useComposerStore } from "@/stores/composer";

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

/** 无会话落地态：路由 "/"，发送后跳转新建会话 */
function renderAtRoot() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<ChatView />} />
          <Route path="/sessions/:sessionId" element={<ChatView />} />
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
  mockState.models = [];
  mockState.session = { id: "s1", agent_id: "a1", title: "并发问题排查" };
  mockState.lastPath = "";
  mockState.lastBody = null;
  mockState.tokens = [];
  mockState.createCalls = 0;
  useComposerStore.setState({ modelOverride: null, webSearch: false, thinking: false });
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

test("顶部展示当前会话标题与调用链入口", async () => {
  renderAt("s1");
  expect(await screen.findByText("并发问题排查")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "查看调用链" })).toHaveAttribute(
    "href",
    "/admin/sessions/s1",
  );
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

test("无会话展示居中落地态：欢迎语、大输入框与示例、@// 提示", async () => {
  mockState.agents = [{ id: "a1", name: "代码专家", emoji: "💻" }];
  renderAtRoot();
  expect(await screen.findByText("贴代码给我")).toBeInTheDocument();
  expect(screen.getByPlaceholderText("输入问题，Enter 发送")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "帮我 review 这段" })).toBeInTheDocument();
  expect(screen.getByText(/命令/)).toBeInTheDocument();
});

test("落地态输入发送创建新会话并走同一发送路径", async () => {
  renderAtRoot();
  await userEvent.type(screen.getByPlaceholderText("输入问题，Enter 发送"), "你好{Enter}");
  await waitFor(() => expect(mockState.lastPath).toBe("/api/v1/sessions/new-1/messages"));
  expect(mockState.lastBody).toEqual({ content: "你好", mentions: [], attachment_ids: [] });
});

test("默认不携带 web_search", async () => {
  renderAtRoot();
  await userEvent.type(screen.getByPlaceholderText("输入问题，Enter 发送"), "你好{Enter}");
  await waitFor(() => expect(mockState.lastBody).not.toBeNull());
  expect(mockState.lastBody).not.toHaveProperty("web_search");
});

test("开启联网搜索后请求体带 web_search", async () => {
  renderAtRoot();
  await userEvent.click(screen.getByRole("button", { name: "联网搜索" }));
  await userEvent.type(screen.getByPlaceholderText("输入问题，Enter 发送"), "搜一下{Enter}");
  await waitFor(() => expect(mockState.lastBody).not.toBeNull());
  expect(mockState.lastBody).toMatchObject({ content: "搜一下", web_search: true });
});

test("模型支持深度思考时请求体带 thinking（默认 false，即关掉默认开启的思考）", async () => {
  useComposerStore.setState({ modelOverride: "think-model" });
  mockState.models = [{ name: "think-model", size_mb: null, capabilities: ["thinking"] }];
  renderAtRoot();
  await userEvent.type(screen.getByPlaceholderText("输入问题，Enter 发送"), "你好{Enter}");
  await waitFor(() => expect(mockState.lastBody).not.toBeNull());
  expect(mockState.lastBody).toMatchObject({ thinking: false });
});

test("模型不支持深度思考时不上报 thinking", async () => {
  useComposerStore.setState({ modelOverride: "plain-model" });
  mockState.models = [{ name: "plain-model", size_mb: null, capabilities: ["completion"] }];
  renderAtRoot();
  await userEvent.type(screen.getByPlaceholderText("输入问题，Enter 发送"), "你好{Enter}");
  await waitFor(() => expect(mockState.lastBody).not.toBeNull());
  expect(mockState.lastBody).not.toHaveProperty("thinking");
});

test("落地态拖入多个附件只创建一个会话并逐个上传", async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    if (String(input).includes("/attachments")) {
      return new Response(
        JSON.stringify({
          id: `att${fetchMock.mock.calls.length}`,
          original_name: "a.png",
          kind: "image",
          size_bytes: 4,
        }),
        { status: 201 },
      );
    }
    return new Response(new Blob(["img"]), { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  URL.createObjectURL = vi.fn(() => "blob:x");
  URL.revokeObjectURL = vi.fn();

  renderAtRoot();
  const files = [
    new File(["png"], "a.png", { type: "image/png" }),
    new File(["png"], "b.png", { type: "image/png" }),
  ];
  fireEvent.drop(screen.getByTestId("composer-dropzone"), {
    dataTransfer: { types: ["Files"], files },
  });

  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  // 只建一次会话：两次上传都落到同一个新会话
  for (const call of fetchMock.mock.calls) {
    expect(String(call[0])).toContain("/api/v1/sessions/new-1/attachments");
  }
  expect(mockState.createCalls).toBe(1);
});

test("发送后用户消息立即显示，不等模型返回", async () => {
  renderAt("s1");
  await userEvent.type(screen.getByPlaceholderText("输入问题，Enter 发送"), "我的问题{Enter}");
  // 本文件的流式 mock 永不结束；用户消息必须此刻就已渲染（乐观插入）
  expect(await screen.findByText("我的问题")).toBeInTheDocument();
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
  // [n] 列表项展示章节路径
  expect(screen.getByText(/· 第3章 › 3\.1 核心参数/)).toBeInTheDocument();
  await userEvent.click(link);
  expect(await screen.findByText("混合检索片段")).toBeInTheDocument();
  expect(screen.getByText(/第 3 页/)).toBeInTheDocument();
  // 抽屉里展示同一份章节路径
  expect(
    within(screen.getByLabelText("引用依据")).getByText("第3章 › 3.1 核心参数"),
  ).toBeInTheDocument();
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
  // 名字会同时出现在徽标文字与"名字首字"头像里，因此用 findAllByText
  expect((await screen.findAllByText("甲")).length).toBeGreaterThan(0);
  // 接力标签与名字分属不同元素，分别断言（可能有多个接力消息）
  expect((await screen.findAllByText(/接力/)).length).toBeGreaterThan(0);
  expect(screen.getAllByText("乙").length).toBeGreaterThan(0);
  expect(screen.getByRole("link", { name: "查看调用链" })).toHaveAttribute(
    "href",
    "/admin/sessions/s1",
  );
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
    screen.getByTestId("attachment-input"),
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
    screen.getByTestId("attachment-input"),
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

test("选择模型后发送携带 model_override", async () => {
  mockState.models = [{ name: "qwen2.5:7b", size_mb: 4096 }];
  renderAt("s1");
  await userEvent.click(screen.getByRole("button", { name: "选择模型" }));
  await userEvent.click(await screen.findByText("qwen2.5:7b"));
  await userEvent.type(screen.getByPlaceholderText("输入问题，Enter 发送"), "带模型{Enter}");
  await waitFor(() =>
    expect(mockState.lastBody).toEqual({
      content: "带模型",
      mentions: [],
      attachment_ids: [],
      model_override: "qwen2.5:7b",
    }),
  );
});

test("token 经 rAF 合帧后完整渲染", async () => {
  mockState.tokens = ["合", "帧"];
  renderAt("s1");
  await userEvent.type(screen.getByPlaceholderText("输入问题，Enter 发送"), "hi{Enter}");
  expect(await screen.findByText(/合帧/)).toBeInTheDocument();
});

test("单帧超大 token 量降级为纯文本渲染", async () => {
  mockState.tokens = ["**不加粗**" + "长".repeat(9000)];
  renderAt("s1");
  await userEvent.type(screen.getByPlaceholderText("输入问题，Enter 发送"), "hi{Enter}");
  expect(await screen.findByText(/\*\*不加粗\*\*/)).toBeInTheDocument();
  expect(screen.queryByText("不加粗", { selector: "strong" })).not.toBeInTheDocument();
});
