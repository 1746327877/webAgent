import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import MarkdownContent from "@/components/chat/MarkdownContent";

test("正文里的 weixin:// 渲染为可点击链接（href 不被清空）", async () => {
  render(<MarkdownContent content="点击支付链接：weixin://wxpay/bizpayurl?pr=5QQN6IHVP3iImz24" />);
  const link = await screen.findByRole("link", { name: /weixin:\/\/wxpay/ });
  expect(link).toHaveAttribute("href", "weixin://wxpay/bizpayurl?pr=5QQN6IHVP3iImz24");
});

test("正文里的 markdown 图片渲染为可查看的图", async () => {
  render(<MarkdownContent content="扫码支付：![二维码](https://a.com/q.png)" />);
  const img = await screen.findByAltText("二维码");
  expect(img).toHaveAttribute("src", "https://a.com/q.png");
  expect(img.closest("a")).toHaveAttribute("href", "https://a.com/q.png");
});

test("写在行内代码里的链接也能点（模型经常这么写）", async () => {
  render(
    <MarkdownContent content={"点击支付链接：`weixin://wxpay/bizpayurl?pr=5QQN6IHVP3iImz24`\n或扫码"} />,
  );
  const link = await screen.findByRole("link", { name: "weixin://wxpay/bizpayurl?pr=5QQN6IHVP3iImz24" });
  expect(link).toHaveAttribute("href", "weixin://wxpay/bizpayurl?pr=5QQN6IHVP3iImz24");
  expect(link).not.toHaveAttribute("target");
});

test("行内代码里的普通文本仍是代码", async () => {
  render(<MarkdownContent content={"比如 `npm run dev` 这样"} />);
  expect(await screen.findByText("npm run dev")).toBeInTheDocument();
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
});

test("多行代码块里的 URL 不会被链接化", async () => {
  render(<MarkdownContent content={"```bash\ncurl weixin://wxpay?pr=abc\n```"} />);
  await screen.findByText("复制");
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
});

test("白名单外的 scheme 不会变成可点链接", async () => {
  const { container } = render(<MarkdownContent content="[点我](javascript:alert(1))" />);
  await screen.findByText("点我");
  // react-markdown 会把危险协议清成空 href（甚至不设 href），无论哪种都不能带 javascript:
  expect(container.querySelector("a")?.getAttribute("href") ?? "").not.toContain("javascript");
});

test("渲染代码块与复制按钮", async () => {
  render(<MarkdownContent content={"```python\nprint('hi')\n```"} />);
  expect(await screen.findByText("复制")).toBeInTheDocument();
  const pre = document.querySelector("pre");
  expect(pre).not.toBeNull();
  // shiki 的内联样式必须透传到 <pre>，否则深色 token 在浅色主题下不可读
  expect(pre?.getAttribute("style")).toContain("background-color");
});
