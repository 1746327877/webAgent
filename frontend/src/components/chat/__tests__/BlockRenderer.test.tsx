import { act, render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";

import BlockRenderer from "@/components/chat/BlockRenderer";
import { useUiStore } from "@/stores/ui";

afterEach(() => {
  act(() => {
    useUiStore.setState({ thinkingDefaultOpen: false });
  });
});

test("渲染 tool_call 卡片", () => {
  render(
    <BlockRenderer
      block={{ type: "tool_call", id: "c1", tool: "time_now", args: "{}" }}
    />,
  );
  expect(screen.getByText(/time_now/)).toBeInTheDocument();
});

test("对象参数渲染为 JSON 文本而非 [object Object]", () => {
  render(
    <BlockRenderer
      block={{ type: "tool_call", id: "c1", tool: "search", args: { query: "x" } }}
    />,
  );
  expect(screen.getByText('{"query":"x"}')).toBeInTheDocument();
  expect(screen.queryByText(/\[object Object\]/)).not.toBeInTheDocument();
});

test("空对象参数不渲染参数摘要", () => {
  render(
    <BlockRenderer
      block={{ type: "tool_call", id: "c1", tool: "time_now", args: {} }}
    />,
  );
  expect(screen.getByText(/time_now/)).toBeInTheDocument();
  expect(screen.queryByText("{}")).not.toBeInTheDocument();
  expect(screen.queryByText(/\[object Object\]/)).not.toBeInTheDocument();
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

test("流式思考链自动展开并显示思考中", () => {
  render(
    <BlockRenderer block={{ type: "thinking", content: "推理中内容", duration_ms: null }} streaming />,
  );
  const details = screen.getByText("思考中…").closest("details");
  expect(details).toHaveAttribute("open");
  expect(screen.getByText("推理中内容")).toBeInTheDocument();
});

test("完成的思考链默认折叠并显示用时", () => {
  render(<BlockRenderer block={{ type: "thinking", content: "推理完成", duration_ms: 3100 }} />);
  const details = screen.getByText("已深度思考 · 用时 3.1s").closest("details");
  expect(details).not.toHaveAttribute("open");
});

test("默认展开设置对历史消息生效", () => {
  useUiStore.setState({ thinkingDefaultOpen: true });
  render(<BlockRenderer block={{ type: "thinking", content: "历史推理", duration_ms: 1200 }} />);
  expect(screen.getByText("历史推理").closest("details")).toHaveAttribute("open");
});

test("degraded 时纯文本渲染不解析 markdown", () => {
  render(<BlockRenderer block={{ type: "text", content: "**粗体**" }} degraded />);
  expect(screen.getByText("**粗体**")).toBeInTheDocument();
});
