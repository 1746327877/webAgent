import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { Tabs, TabsPanel } from "@/components/ui/tabs";

test("渲染标签、切换回调与 aria-selected", async () => {
  const onChange = vi.fn();
  render(
    <Tabs
      value="a"
      onChange={onChange}
      items={[
        { key: "a", label: "甲" },
        { key: "b", label: "乙" },
      ]}
      ariaLabel="分区"
    />,
  );
  expect(screen.getByRole("tab", { name: "甲" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("tab", { name: "乙" })).toHaveAttribute("aria-selected", "false");

  await userEvent.click(screen.getByRole("tab", { name: "乙" }));
  expect(onChange).toHaveBeenCalledWith("b");
});

test("TabsPanel 带淡入上滑过渡，并尊重 reduced-motion", () => {
  render(<TabsPanel>内容</TabsPanel>);
  const panel = screen.getByText("内容");
  expect(panel.className).toContain("animate-in");
  expect(panel.className).toContain("fade-in-0");
  expect(panel.className).toContain("slide-in-from-bottom-1");
  expect(panel.className).toContain("motion-reduce:animate-none");
});
