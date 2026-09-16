import { beforeEach, expect, test } from "vitest";
import { toast, useToastStore } from "@/stores/toast";

beforeEach(() => {
  useToastStore.getState().clear();
});

test("toast.success/error 入队，dismiss 可移除指定项", () => {
  const id = toast.success("已保存");
  toast.error("保存失败");

  const toasts = useToastStore.getState().toasts;
  expect(toasts.map((t) => t.message)).toEqual(["已保存", "保存失败"]);
  expect(toasts.map((t) => t.variant)).toEqual(["success", "error"]);

  useToastStore.getState().dismiss(id);
  expect(useToastStore.getState().toasts.map((t) => t.message)).toEqual(["保存失败"]);
});
