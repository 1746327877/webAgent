import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import Composer from "@/components/chat/Composer";

const AGENTS = [
  { id: "a1", name: "深度思考", emoji: "🧠" },
  { id: "a2", name: "代码专家", emoji: "💻" },
];

test("Enter 触发发送并清空输入", async () => {
  const onSend = vi.fn();
  render(<Composer onSend={onSend} onStop={vi.fn()} generating={false} />);
  const input = screen.getByPlaceholderText("输入问题，Enter 发送");
  await userEvent.type(input, "你好{Enter}");
  expect(onSend).toHaveBeenCalledWith("你好", []);
  expect((input as HTMLInputElement).value).toBe("");
});

test("generating 时点击停止", async () => {
  const onStop = vi.fn();
  render(<Composer onSend={vi.fn()} onStop={onStop} generating={true} />);
  await userEvent.click(screen.getByRole("button", { name: "停止" }));
  expect(onStop).toHaveBeenCalled();
});

test("@ 弹出并选择后提交携带 mention", async () => {
  const onSend = vi.fn();
  render(<Composer onSend={onSend} onStop={vi.fn()} generating={false} agents={AGENTS} />);
  const input = screen.getByPlaceholderText("输入问题，Enter 发送");
  await userEvent.type(input, "@深度");
  expect(await screen.findByText("深度思考")).toBeInTheDocument();
  await userEvent.click(screen.getByText("深度思考"));
  expect((input as HTMLInputElement).value).toContain("@深度思考");
  await userEvent.type(input, " 帮我看看");
  await userEvent.type(input, "{Enter}");
  expect(onSend).toHaveBeenCalledWith("@深度思考 帮我看看", ["a1"]);
});

test("无 @ 不产生 mentions", async () => {
  const onSend = vi.fn();
  render(<Composer onSend={onSend} onStop={vi.fn()} generating={false} agents={AGENTS} />);
  await userEvent.type(screen.getByPlaceholderText("输入问题，Enter 发送"), "hello{Enter}");
  expect(onSend).toHaveBeenCalledWith("hello", []);
});
