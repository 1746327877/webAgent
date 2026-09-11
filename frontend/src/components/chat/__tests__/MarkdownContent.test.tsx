import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import MarkdownContent from "@/components/chat/MarkdownContent";

test("渲染代码块与复制按钮", async () => {
  render(<MarkdownContent content={"```python\nprint('hi')\n```"} />);
  expect(await screen.findByText("复制")).toBeInTheDocument();
  expect(document.querySelector("pre")).not.toBeNull();
});
