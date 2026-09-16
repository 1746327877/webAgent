import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, expect, test, vi } from "vitest";
import type { SessionItem } from "@/api/sessions";

const mocks = vi.hoisted(() => ({
  useSessions: vi.fn(),
  updateMutate: vi.fn(),
  deleteMutate: vi.fn(),
  bulkDelete: vi.fn(),
}));

vi.mock("@/api/sessions", () => ({
  useSessions: mocks.useSessions,
  useCreateSession: () => ({ mutate: vi.fn(), mutateAsync: vi.fn() }),
  useUpdateSession: () => ({ mutate: mocks.updateMutate }),
  useDeleteSession: () => ({ mutate: mocks.deleteMutate }),
  useBulkDeleteSessions: () => ({ mutateAsync: mocks.bulkDelete, isPending: false }),
}));

vi.mock("@/api/agents", () => ({
  useAgents: () => ({ data: [] }),
}));

import SessionSidebar from "@/components/sidebar/SessionSidebar";
import { useUiStore } from "@/stores/ui";

function makeSession(overrides: Partial<SessionItem> = {}): SessionItem {
  return {
    id: "s1",
    title: "Java 学习",
    agent_id: null,
    pinned: false,
    archived: false,
    last_message_at: new Date().toISOString(),
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    ...overrides,
  };
}

function queryResult(items: SessionItem[]) {
  return {
    data: { pages: [{ items, total: items.length }] },
    isLoading: false,
    fetchNextPage: vi.fn(),
    hasNextPage: false,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.useSessions.mockReturnValue(queryResult([]));
});

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="pathname">{location.pathname}</div>;
}

test("渲染会话标题", () => {
  mocks.useSessions.mockReturnValue(queryResult([makeSession()]));
  render(
    <MemoryRouter>
      <SessionSidebar />
    </MemoryRouter>,
  );
  expect(screen.getByText("Java 学习")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "📊 可观测性" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "🔑 API 密钥" })).toHaveAttribute("href", "/keys");
});

test("删除当前会话后跳回 /", () => {
  vi.spyOn(window, "confirm").mockReturnValue(true);
  mocks.useSessions.mockReturnValue(queryResult([makeSession()]));
  render(
    <MemoryRouter initialEntries={["/sessions/s1"]}>
      <Routes>
        <Route
          path="/"
          element={
            <>
              <SessionSidebar />
              <LocationProbe />
            </>
          }
        >
          <Route path="sessions/:sessionId" element={<div>chat view</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
  expect(screen.getByTestId("pathname").textContent).toBe("/sessions/s1");
  fireEvent.click(screen.getByText("删"));
  expect(screen.getByTestId("pathname").textContent).toBe("/");
  vi.restoreAllMocks();
});

test("置顶项进入「置顶」分组且保持接口返回顺序", () => {
  const pinnedOld = makeSession({
    id: "p-old",
    title: "置顶旧",
    pinned: true,
    last_message_at: "2020-01-01T00:00:00Z",
  });
  const pinnedNew = makeSession({ id: "p-new", title: "置顶新", pinned: true });
  const normal = makeSession({ id: "n1", title: "普通会话" });
  mocks.useSessions.mockReturnValue(queryResult([pinnedOld, pinnedNew, normal]));
  render(
    <MemoryRouter>
      <SessionSidebar />
    </MemoryRouter>,
  );
  expect(screen.getByTestId("session-group-置顶")).toBeInTheDocument();
  const links = screen.getAllByRole("link").map((a) => a.textContent ?? "");
  expect(links[0]).toContain("置顶旧");
  expect(links[1]).toContain("置顶新");
  expect(links[2]).toContain("普通会话");
});

test("归档视图请求 archived=true，提供恢复并隐藏置顶/归档", () => {
  const archived = makeSession({ id: "a1", title: "已归档会话", archived: true });
  mocks.useSessions.mockImplementation((_query: string, isArchived = false) =>
    queryResult(isArchived ? [archived] : []),
  );
  render(
    <MemoryRouter>
      <SessionSidebar />
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByRole("button", { name: "查看归档" }));
  expect(mocks.useSessions).toHaveBeenLastCalledWith("", true);
  expect(screen.getByText("已归档会话")).toBeInTheDocument();
  expect(screen.getByText("恢复")).toBeInTheDocument();
  expect(screen.queryByText("归档")).not.toBeInTheDocument();
  expect(screen.queryByText("置顶")).not.toBeInTheDocument();
  expect(screen.getByText("删")).toBeInTheDocument();
  fireEvent.click(screen.getByText("恢复"));
  expect(mocks.updateMutate).toHaveBeenCalledWith({ id: "a1", patch: { archived: false } });
  fireEvent.click(screen.getByRole("button", { name: "返回" }));
  expect(mocks.useSessions).toHaveBeenLastCalledWith("", false);
});

test("切换主题按钮为根节点添加 dark class", () => {
  useUiStore.setState({ theme: "light" });
  render(
    <MemoryRouter>
      <SessionSidebar />
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByRole("button", { name: "切换主题" }));
  expect(document.documentElement.classList.contains("dark")).toBe(true);
  document.documentElement.classList.remove("dark");
});

test("多选模式：分组复选框整组选中，就近确认后批量删除", async () => {
  const items = [
    makeSession({ id: "s1", title: "会话一" }),
    makeSession({ id: "s2", title: "会话二" }),
  ];
  mocks.useSessions.mockReturnValue(queryResult(items));
  mocks.bulkDelete.mockResolvedValue({ deleted: 2 });
  render(
    <MemoryRouter>
      <SessionSidebar />
    </MemoryRouter>,
  );

  fireEvent.click(screen.getByRole("button", { name: "多选" }));
  expect(screen.getByText("已选 0")).toBeInTheDocument();

  // 勾"今天"分组标题的复选框 → 整组选中
  fireEvent.click(screen.getByRole("checkbox", { name: "全选 今天" }));
  expect(screen.getByText("已选 2")).toBeInTheDocument();

  // 第一次点击只进入就近确认，不直接删除
  fireEvent.click(screen.getByRole("button", { name: "删除选中" }));
  expect(screen.getByText("删除 2 条？不可恢复")).toBeInTheDocument();
  expect(mocks.bulkDelete).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole("button", { name: "确认删除" }));
  await waitFor(() => expect(mocks.bulkDelete).toHaveBeenCalledWith(["s1", "s2"]));
});

test("多选模式：就近确认里点取消则不删除", () => {
  mocks.useSessions.mockReturnValue(queryResult([makeSession({ id: "s1", title: "会话一" })]));
  render(
    <MemoryRouter>
      <SessionSidebar />
    </MemoryRouter>,
  );

  fireEvent.click(screen.getByRole("button", { name: "多选" }));
  fireEvent.click(screen.getByRole("checkbox", { name: "全选 今天" }));
  fireEvent.click(screen.getByRole("button", { name: "删除选中" }));
  fireEvent.click(screen.getByRole("button", { name: "取消" }));
  expect(mocks.bulkDelete).not.toHaveBeenCalled();
  expect(screen.queryByText(/不可恢复/)).not.toBeInTheDocument();
});
