import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import MessageActions from "@/components/chat/MessageActions";
import type { MessageItemData } from "@/api/sessions";

function makeMessage(overrides: Partial<MessageItemData> = {}): MessageItemData {
  return {
    id: "m1",
    role: "assistant",
    blocks: [{ type: "text", content: "hi" }],
    status: "done",
    rating: null,
    error: null,
    created_at: "2026-09-11T10:00:00Z",
    ...overrides,
  };
}

function renderActions(overrides: Partial<MessageItemData> = {}, handlers: {
  onRegenerate?: (id: string) => void;
  onEdit?: (id: string, text: string) => void;
  onRate?: (id: string, rating: 1 | -1) => void;
} = {}) {
  return render(
    <MessageActions
      message={makeMessage(overrides)}
      onRegenerate={handlers.onRegenerate ?? vi.fn()}
      onEdit={handlers.onEdit ?? vi.fn()}
      onRate={handlers.onRate ?? vi.fn()}
    />,
  );
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

test("复制按钮以图标渲染并带中文可访问名与提示", () => {
  renderActions();
  const button = screen.getByRole("button", { name: "复制" });
  expect(button).toHaveAttribute("title", "复制");
  expect(button).toHaveAttribute("type", "button");
  expect(button.querySelector("svg")).toBeInTheDocument();
  expect(button.textContent).toBe("");
});

test("复制成功后切换为已复制，约2秒后复原", async () => {
  vi.useFakeTimers();
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText },
    configurable: true,
  });
  renderActions();

  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "复制" }));
  });
  expect(writeText).toHaveBeenCalledWith("hi");
  expect(screen.getByRole("button", { name: "已复制" })).toHaveAttribute("title", "已复制");
  expect(screen.queryByRole("button", { name: "复制" })).not.toBeInTheDocument();

  act(() => {
    vi.advanceTimersByTime(2000);
  });
  expect(screen.getByRole("button", { name: "复制" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "已复制" })).not.toBeInTheDocument();
});

test("重新生成按钮以图标渲染并回调", async () => {
  const onRegenerate = vi.fn();
  renderActions({}, { onRegenerate });
  const button = screen.getByRole("button", { name: "重新生成" });
  expect(button).toHaveAttribute("title", "重新生成");
  expect(button.querySelector("svg")).toBeInTheDocument();
  await userEvent.click(button);
  expect(onRegenerate).toHaveBeenCalledWith("m1");
});

test("有用/无用图标按钮分别回调 1 与 -1", async () => {
  const onRate = vi.fn();
  renderActions({}, { onRate });
  const up = screen.getByRole("button", { name: "有用" });
  expect(up).toHaveAttribute("title", "有用");
  expect(up.querySelector("svg")).toBeInTheDocument();
  await userEvent.click(up);
  expect(onRate).toHaveBeenCalledWith("m1", 1);

  const down = screen.getByRole("button", { name: "无用" });
  expect(down).toHaveAttribute("title", "无用");
  expect(down.querySelector("svg")).toBeInTheDocument();
  await userEvent.click(down);
  expect(onRate).toHaveBeenCalledWith("m1", -1);
});

test("已评分项高亮，未评分项保持静默样式", () => {
  const { rerender } = renderActions();
  expect(screen.getByRole("button", { name: "有用" })).not.toHaveClass("text-foreground");
  expect(screen.getByRole("button", { name: "无用" })).not.toHaveClass("text-foreground");

  rerender(
    <MessageActions
      message={makeMessage({ rating: 1 })}
      onRegenerate={vi.fn()}
      onEdit={vi.fn()}
      onRate={vi.fn()}
    />,
  );
  const up = screen.getByRole("button", { name: "有用" });
  expect(up).toHaveClass("text-foreground");
  expect(up).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByRole("button", { name: "无用" })).not.toHaveClass("text-foreground");
  expect(screen.getByRole("button", { name: "无用" })).toHaveAttribute("aria-pressed", "false");

  rerender(
    <MessageActions
      message={makeMessage({ rating: -1 })}
      onRegenerate={vi.fn()}
      onEdit={vi.fn()}
      onRate={vi.fn()}
    />,
  );
  expect(screen.getByRole("button", { name: "无用" })).toHaveClass("text-foreground");
  expect(screen.getByRole("button", { name: "有用" })).not.toHaveClass("text-foreground");
});

test("用户消息以铅笔图标编辑，保存并重发仍为文本按钮", async () => {
  const onEdit = vi.fn();
  renderActions({ role: "user" }, { onEdit });
  const editButton = screen.getByRole("button", { name: "编辑" });
  expect(editButton).toHaveAttribute("title", "编辑");
  expect(editButton.querySelector("svg")).toBeInTheDocument();

  await userEvent.click(editButton);
  const textarea = screen.getByRole("textbox");
  await userEvent.clear(textarea);
  await userEvent.type(textarea, "改后的内容");
  await userEvent.click(screen.getByRole("button", { name: "保存并重发" }));
  expect(onEdit).toHaveBeenCalledWith("m1", "改后的内容");
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
});

test("取消编辑退出编辑态且不回调", async () => {
  const onEdit = vi.fn();
  renderActions({ role: "user" }, { onEdit });
  await userEvent.click(screen.getByRole("button", { name: "编辑" }));
  await userEvent.click(screen.getByRole("button", { name: "取消" }));
  expect(onEdit).not.toHaveBeenCalled();
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "编辑" })).toBeInTheDocument();
});

test("助手消息不显示编辑，用户消息不显示评分", () => {
  const { unmount } = renderActions();
  expect(screen.queryByRole("button", { name: "编辑" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "有用" })).toBeInTheDocument();
  unmount();

  renderActions({ role: "user" });
  expect(screen.queryByRole("button", { name: "有用" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "无用" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "重新生成" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "编辑" })).toBeInTheDocument();
});
