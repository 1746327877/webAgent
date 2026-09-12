import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import MessageItem from "@/components/chat/MessageItem";
import type { MessageItemData } from "@/api/sessions";

function makeMessage(overrides: Partial<MessageItemData> = {}): MessageItemData {
  return {
    id: "m1",
    role: "assistant",
    blocks: [{ type: "text", content: "部分回答" }],
    status: "done",
    rating: null,
    error: null,
    created_at: "2026-09-11T10:00:00Z",
    ...overrides,
  };
}

test("error 状态在内容下方显示失败提示", () => {
  render(<MessageItem message={makeMessage({ status: "error", error: "连接失败" })} />);
  expect(screen.getByText("部分回答")).toBeInTheDocument();
  expect(screen.getByText("生成失败，可点「重新生成」重试")).toBeInTheDocument();
});

test("stopped 状态显示已停止", () => {
  render(<MessageItem message={makeMessage({ status: "stopped" })} />);
  expect(screen.getByText("已停止")).toBeInTheDocument();
});

test("error 状态点击重试回调携带消息 id", async () => {
  const onRetry = vi.fn();
  render(
    <MessageItem message={makeMessage({ status: "error", error: "连接失败" })} onRetry={onRetry} />,
  );
  await userEvent.click(screen.getByRole("button", { name: "重试" }));
  expect(onRetry).toHaveBeenCalledWith("m1");
});
