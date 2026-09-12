import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import BlockRenderer from "@/components/chat/BlockRenderer";

test("渲染 tool_call 卡片", () => {
  render(
    <BlockRenderer
      block={{ type: "tool_call", id: "c1", tool: "time_now", args: "{}" }}
    />,
  );
  expect(screen.getByText(/time_now/)).toBeInTheDocument();
});

test("渲染 tool_result 状态与耗时", () => {
  render(
    <BlockRenderer
      block={{
        type: "tool_result",
        id: "c1",
        tool: "time_now",
        status: "ok",
        elapsed_ms: 12,
        preview: "2026-09-11 星期五",
      }}
    />,
  );
  expect(screen.getByText(/12ms/)).toBeInTheDocument();
  expect(screen.getByText(/2026-09-11/)).toBeInTheDocument();
});
