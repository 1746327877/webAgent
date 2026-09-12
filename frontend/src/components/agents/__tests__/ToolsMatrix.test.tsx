import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import ToolsMatrix from "@/components/agents/ToolsMatrix";

const TOOLS = [
  { id: "1", slug: "time_now", name: "当前时间", description: "d", category: "system", is_system: true },
  { id: "2", slug: "kb_search", name: "知识库检索", description: "d", category: "knowledge", is_system: true },
];

test("勾选触发 onChange", async () => {
  const onChange = vi.fn();
  render(<ToolsMatrix tools={TOOLS} value={[]} onChange={onChange} />);
  await userEvent.click(screen.getByLabelText("当前时间"));
  expect(onChange).toHaveBeenCalledWith(["time_now"]);
});
