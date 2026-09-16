import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import Toaster from "@/components/ui/toaster";
import { toast, useToastStore } from "@/stores/toast";

beforeEach(() => {
  useToastStore.getState().clear();
});

afterEach(() => {
  vi.useRealTimers();
});

test("渲染 toast 并可手动关闭", async () => {
  render(<Toaster />);
  act(() => {
    toast.success("已保存");
  });

  expect(screen.getByText("已保存")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "关闭提示" }));
  expect(screen.queryByText("已保存")).not.toBeInTheDocument();
});

test("成功 toast 3 秒后自动消失", () => {
  vi.useFakeTimers();
  render(<Toaster />);
  act(() => {
    toast.success("已发布");
  });
  expect(screen.getByText("已发布")).toBeInTheDocument();

  act(() => {
    vi.advanceTimersByTime(3000);
  });
  expect(screen.queryByText("已发布")).not.toBeInTheDocument();
});
