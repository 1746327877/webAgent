import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import Composer from "@/components/chat/Composer";

test("Enter 触发发送并清空输入", async () => {
  const onSend = vi.fn();
  render(<Composer onSend={onSend} onStop={vi.fn()} generating={false} />);
  const input = screen.getByPlaceholderText("输入问题，Enter 发送");
  await userEvent.type(input, "你好{Enter}");
  expect(onSend).toHaveBeenCalledWith("你好");
  expect((input as HTMLInputElement).value).toBe("");
});

test("generating 时点击停止", async () => {
  const onStop = vi.fn();
  render(<Composer onSend={vi.fn()} onStop={onStop} generating={true} />);
  await userEvent.click(screen.getByRole("button", { name: "停止" }));
  expect(onStop).toHaveBeenCalled();
});
