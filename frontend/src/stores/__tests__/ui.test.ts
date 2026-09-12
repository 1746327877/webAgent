import { beforeEach, expect, test } from "vitest";
import { useUiStore } from "@/stores/ui";

beforeEach(() => {
  localStorage.clear();
  document.documentElement.classList.remove("dark");
  useUiStore.setState({ theme: "light", thinkingDefaultOpen: false });
});

test("toggleTheme 切换根节点 class 并持久化", () => {
  useUiStore.getState().toggleTheme();
  expect(useUiStore.getState().theme).toBe("dark");
  expect(document.documentElement.classList.contains("dark")).toBe(true);
  expect(localStorage.getItem("ui-theme")).toBe("dark");
  useUiStore.getState().toggleTheme();
  expect(document.documentElement.classList.contains("dark")).toBe(false);
});

test("setThinkingDefaultOpen 持久化", () => {
  useUiStore.getState().setThinkingDefaultOpen(true);
  expect(useUiStore.getState().thinkingDefaultOpen).toBe(true);
  expect(localStorage.getItem("ui-thinking-open")).toBe("1");
});
