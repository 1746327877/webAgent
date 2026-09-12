import { cleanup, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, expect, test, vi } from "vitest";
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

vi.mock("@/api/sessions", () => ({
  useCreateSession: () => ({ mutateAsync: vi.fn() }),
  useMessages: () => ({ data: [] }),
  useSession: () => ({ data: { id: "s1", agent_id: "a1" } }),
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

afterEach(() => {
  cleanup();
  useChatStreamStore.getState().clear();
});

test("其他会话的流式叠加层不会泄漏到当前会话", () => {
  useChatStreamStore.setState({
    active: { id: "m-other", sessionId: "other", content: "泄漏内容", thinking: "" },
    error: null,
  });
  renderAt("current");
  expect(screen.queryByText("泄漏内容")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "停止" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "发送" })).toBeInTheDocument();
});

test("当前会话的流式叠加层正常显示且可停止", () => {
  useChatStreamStore.setState({
    active: { id: "m-current", sessionId: "current", content: "进行中内容", thinking: "" },
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
