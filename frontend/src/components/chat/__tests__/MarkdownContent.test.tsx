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

test("模型把表头写在说明文字同一行时也能渲染成表格", async () => {
  render(
    <MarkdownContent
      content={"待办：| 事项 | 责任人 |\n|---|---|\n| 确认是否为本地功能 | 未指定 |"}
    />,
  );
  const headers = await screen.findAllByRole("columnheader");
  expect(headers.map((h) => h.textContent)).toEqual(["事项", "责任人"]);
  // 表头默认居中
  expect(headers[0]).toHaveClass("text-center");
  expect(screen.getAllByRole("cell").map((c) => c.textContent)).toEqual([
    "确认是否为本地功能",
    "未指定",
  ]);
  // 说明文字保留，另起一行
  expect(screen.getByText("待办：")).toBeInTheDocument();
});

test("列表项后面直接跟表格也能渲染（表格不能打断段落，需补空行）", async () => {
  render(
    <MarkdownContent
      content={"4. **待办**：\n| 事项 | 责任人 |\n| :--- | :--- |\n| 验证代码逻辑 | 系统/测试人员 |"}
    />,
  );
  const headers = await screen.findAllByRole("columnheader");
  expect(headers.map((h) => h.textContent)).toEqual(["事项", "责任人"]);
  expect(screen.getAllByRole("cell").map((c) => c.textContent)).toEqual([
    "验证代码逻辑",
    "系统/测试人员",
  ]);
});

test("表头：分隔行写成 :--- 时也居中（丢弃 gfm 的内联对齐）", async () => {
  render(<MarkdownContent content={"| 事项 | 值 |\n| :--- | :---: |\n| a | b |"} />);
  const headers = await screen.findAllByRole("columnheader");
  // gfm 会按分隔行加 style="text-align: left"，内联样式会盖掉类名 → 必须丢掉
  for (const header of headers) {
    expect(header).not.toHaveAttribute("style");
    expect(header).toHaveClass("text-center");
  }
});

test("正文里的竖线不会被误判成表格", async () => {
  render(<MarkdownContent content={"A | B 是并列写法\n不是表格"} />);
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  expect(screen.getByText(/A \| B 是并列写法/)).toBeInTheDocument();
});

test("roleBadges 关闭时 `## 我` 仍是普通标题", () => {
  render(<MarkdownContent content={"## 我\n\n你好"} />);
  const heading = screen.getByRole("heading", { name: "我" });
  expect(heading).not.toHaveClass("border-sky-500/40");
});

test("roleBadges 开启时 `## 我` / `## 助手` 渲染成不同颜色的身份框", () => {
  render(
    <MarkdownContent content={"## 我\n\n你好\n\n## 助手\n\n好的\n\n## 我的看法\n\n补充"} roleBadges />,
  );
  const user = screen.getByRole("heading", { name: "我" });
  const assistant = screen.getByRole("heading", { name: "助手" });
  expect(user).toHaveClass("border-sky-500/40");
  expect(assistant).toHaveClass("border-emerald-500/40");
  // 只是包含"我"的标题不误伤
  expect(screen.getByRole("heading", { name: "我的看法" })).not.toHaveClass(
    "border-sky-500/40",
  );
});

test("有序/无序列表补回序号与缩进（Tailwind preflight 会清掉默认样式）", async () => {
  render(<MarkdownContent content={"1. 第一项\n2. 第二项\n\n- 甲\n- 乙"} />);
  const [ordered, unordered] = await screen.findAllByRole("list");
  expect(ordered.tagName).toBe("OL");
  expect(ordered).toHaveClass("list-decimal");
  expect(ordered).toHaveClass("pl-6");
  expect(unordered.tagName).toBe("UL");
  expect(unordered).toHaveClass("list-disc");
  expect(screen.getAllByRole("listitem")).toHaveLength(4);
});

test("markdown 表格渲染出表头与单元格，并包在可横向滚动的容器里", async () => {
  render(
    <MarkdownContent
      content={"| 事项 | 责任人 |\n| --- | --- |\n| 发布 | 张三 |"}
    />,
  );
  const headers = await screen.findAllByRole("columnheader");
  expect(headers.map((h) => h.textContent)).toEqual(["事项", "责任人"]);
  const cells = screen.getAllByRole("cell");
  expect(cells.map((c) => c.textContent)).toEqual(["发布", "张三"]);
  // 列之间要有分隔线，否则多列内容会糊在一起
  expect(cells[0]).toHaveClass("border-r-[1.5px]");
  expect(cells[1]).toHaveClass("last:border-r-0");
  // 表头即使分隔行是 `:---`（gfm 会写内联 text-align:left）也必须居中
  expect(headers[0]).not.toHaveAttribute("style");
  expect(headers[0]).toHaveClass("text-center");
  // 宽度按内容自适应（最宽的列），不能 w-full 撑到页面边缘
  const table = screen.getByRole("table");
  expect(table).not.toHaveClass("w-full");
  // 外层要能横向滚动且不超出容器（超宽表滚动，窄表贴着内容）
  expect(table.parentElement).toHaveClass("overflow-x-auto");
  expect(table.parentElement).toHaveClass("inline-block");
  expect(table.parentElement).toHaveClass("max-w-full");
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
