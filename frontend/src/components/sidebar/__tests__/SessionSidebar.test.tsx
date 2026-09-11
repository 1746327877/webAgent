import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
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

test("渲染会话标题", () => {
  render(
    <MemoryRouter>
      <SessionSidebar />
    </MemoryRouter>,
  );
  expect(screen.getByText("Java 学习")).toBeInTheDocument();
});
