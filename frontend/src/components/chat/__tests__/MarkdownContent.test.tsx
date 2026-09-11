import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import MarkdownContent from "@/components/chat/MarkdownContent";

test("渲染代码块与复制按钮", async () => {
  render(<MarkdownContent content={"```python\nprint('hi')\n```"} />);
  expect(await screen.findByText("复制")).toBeInTheDocument();
  const pre = document.querySelector("pre");
  expect(pre).not.toBeNull();
  // shiki 的内联样式必须透传到 <pre>，否则深色 token 在浅色主题下不可读
  expect(pre?.getAttribute("style")).toContain("background-color");
});
