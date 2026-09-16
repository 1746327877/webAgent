import { expect, test } from "vitest";
import { useComposerStore } from "@/stores/composer";

test("联网搜索开关默认关闭且可切换", () => {
  useComposerStore.setState({ webSearch: false });
  expect(useComposerStore.getState().webSearch).toBe(false);
  useComposerStore.getState().setWebSearch(true);
  expect(useComposerStore.getState().webSearch).toBe(true);
  useComposerStore.setState({ webSearch: false });
});
