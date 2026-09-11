import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import MessageActions from "@/components/chat/MessageActions";

const message = {
  id: "m1",
  role: "assistant",
  blocks: [{ type: "text", content: "hi" }],
  status: "done",
  rating: null,
  error: null,
  created_at: "2026-09-11T10:00:00Z",
};

test("助手消息显示重新生成并回调", async () => {
  const onRegenerate = vi.fn();
  render(<MessageActions message={message} onRegenerate={onRegenerate} onEdit={vi.fn()} onRate={vi.fn()} />);
  await userEvent.click(screen.getByRole("button", { name: "重新生成" }));
  expect(onRegenerate).toHaveBeenCalledWith("m1");
});

test("评分按钮回调", async () => {
  const onRate = vi.fn();
  render(<MessageActions message={message} onRegenerate={vi.fn()} onEdit={vi.fn()} onRate={onRate} />);
  await userEvent.click(screen.getByRole("button", { name: "有用" }));
  expect(onRate).toHaveBeenCalledWith("m1", 1);
});
