import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, expect, test, vi } from "vitest";
import type { SessionItem } from "@/api/sessions";

const mocks = vi.hoisted(() => ({
  useSessions: vi.fn(),
  updateMutate: vi.fn(),
  deleteMutate: vi.fn(),
}));

vi.mock("@/api/sessions", () => ({
  useSessions: mocks.useSessions,
  useCreateSession: () => ({ mutate: vi.fn(), mutateAsync: vi.fn() }),
  useUpdateSession: () => ({ mutate: mocks.updateMutate }),
  useDeleteSession: () => ({ mutate: mocks.deleteMutate }),
}));

vi.mock("@/api/agents", () => ({
  useAgents: () => ({ data: [] }),
}));

import SessionSidebar from "@/components/sidebar/SessionSidebar";

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
  expect(screen.getByText("置顶", { selector: "p" })).toBeInTheDocument();
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
