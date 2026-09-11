import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { expect, test, vi } from "vitest";

vi.mock("@/api/sessions", () => ({
  useSessions: () => ({
    data: {
      pages: [
        {
          items: [
            {
              id: "s1",
              title: "Java 学习",
              pinned: false,
              archived: false,
              last_message_at: "2026-09-11T10:00:00+08:00",
              created_at: "2026-09-11T10:00:00+08:00",
              updated_at: "2026-09-11T10:00:00+08:00",
            },
          ],
          total: 1,
        },
      ],
    },
    isLoading: false,
    fetchNextPage: vi.fn(),
    hasNextPage: false,
  }),
  useCreateSession: () => ({ mutate: vi.fn() }),
  useUpdateSession: () => ({ mutate: vi.fn() }),
  useDeleteSession: () => ({ mutate: vi.fn() }),
}));

import SessionSidebar from "@/components/sidebar/SessionSidebar";

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="pathname">{location.pathname}</div>;
}

test("渲染会话标题", () => {
  render(
    <MemoryRouter>
      <SessionSidebar />
    </MemoryRouter>,
  );
  expect(screen.getByText("Java 学习")).toBeInTheDocument();
});

test("删除当前会话后跳回 /", () => {
  vi.spyOn(window, "confirm").mockReturnValue(true);
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
