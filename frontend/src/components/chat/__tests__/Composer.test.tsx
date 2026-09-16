import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import Composer from "@/components/chat/Composer";

const AGENTS = [
  { id: "a1", name: "深度思考", emoji: "🧠" },
  { id: "a2", name: "代码专家", emoji: "💻" },
  { id: "a3", name: "翻译助手", emoji: "🌐" },
];

test("Enter 触发发送并清空输入", async () => {
  const onSend = vi.fn();
  render(<Composer onSend={onSend} onStop={vi.fn()} generating={false} />);
  const input = screen.getByPlaceholderText("输入问题，Enter 发送");
  await userEvent.type(input, "你好{Enter}");
  expect(onSend).toHaveBeenCalledWith("你好", [], []);
  expect((input as HTMLInputElement).value).toBe("");
});

test("generating 时点击停止", async () => {
  const onStop = vi.fn();
  render(<Composer onSend={vi.fn()} onStop={onStop} generating={true} />);
  await userEvent.click(screen.getByRole("button", { name: "停止" }));
  expect(onStop).toHaveBeenCalled();
});

test("联网搜索按钮未配置时禁用", () => {
  render(<Composer onSend={vi.fn()} onStop={vi.fn()} generating={false} />);
  expect(screen.getByRole("button", { name: "联网搜索" })).toBeDisabled();
});

test("联网搜索按钮切换回调携带目标状态", async () => {
  const onChange = vi.fn();
  render(
    <Composer
      onSend={vi.fn()}
      onStop={vi.fn()}
      generating={false}
      webSearchAvailable
      webSearch={false}
      onWebSearchChange={onChange}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "联网搜索" }));
  expect(onChange).toHaveBeenCalledWith(true);
});

test("@ 弹出并选择后提交携带 mention", async () => {
  const onSend = vi.fn();
  render(<Composer onSend={onSend} onStop={vi.fn()} generating={false} agents={AGENTS} />);
  const input = screen.getByPlaceholderText("输入问题，Enter 发送");
  await userEvent.type(input, "@深度");
  expect(await screen.findByText("深度思考")).toBeInTheDocument();
  await userEvent.click(screen.getByText("深度思考"));
  expect((input as HTMLInputElement).value).toContain("@深度思考");
  await userEvent.type(input, " 帮我看看");
  await userEvent.type(input, "{Enter}");
  expect(onSend).toHaveBeenCalledWith("@深度思考 帮我看看", ["a1"], []);
});

test("无 @ 不产生 mentions", async () => {
  const onSend = vi.fn();
  render(<Composer onSend={onSend} onStop={vi.fn()} generating={false} agents={AGENTS} />);
  await userEvent.type(screen.getByPlaceholderText("输入问题，Enter 发送"), "hello{Enter}");
  expect(onSend).toHaveBeenCalledWith("hello", [], []);
});

test("最多提交 2 个 mention，第三次选择被拒绝", async () => {
  const onSend = vi.fn();
  render(<Composer onSend={onSend} onStop={vi.fn()} generating={false} agents={AGENTS} />);
  const input = screen.getByPlaceholderText("输入问题，Enter 发送");
  await userEvent.type(input, "@");
  await userEvent.click(await screen.findByText("深度思考"));
  await userEvent.type(input, "@");
  await userEvent.click(await screen.findByText("代码专家"));
  await userEvent.type(input, "@");
  expect(await screen.findByText("最多同时 @ 2 个智能体")).toBeInTheDocument();
  await userEvent.click(screen.getByText("翻译助手"));
  // 第三次选择被拒绝：文本与已选 id 均不变
  expect((input as HTMLInputElement).value).not.toContain("@翻译助手");
  await userEvent.type(input, "{Escape}{Enter}");
  expect(onSend).toHaveBeenCalledWith("@深度思考@代码专家@", ["a1", "a2"], []);
});

test("选择图片上报 onAttach，chip 预览可移除，发送携带 attachmentIds", async () => {
  const onAttach = vi.fn();
  const onRemoveAttachment = vi.fn();
  const onSend = vi.fn();
  render(
    <Composer
      onSend={onSend}
      onStop={vi.fn()}
      generating={false}
      attachments={[{ id: "att1", previewUrl: "blob:preview", name: "cat.png", kind: "image" }]}
      onAttach={onAttach}
      onRemoveAttachment={onRemoveAttachment}
    />,
  );
  expect(screen.getByAltText("图片预览")).toHaveAttribute("src", "blob:preview");
  expect(screen.getByText("cat.png")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "移除附件" }));
  expect(onRemoveAttachment).toHaveBeenCalledWith("att1");

  const file = new File(["png"], "cat.png", { type: "image/png" });
  await userEvent.upload(screen.getByTestId("attachment-input"), file);
  expect(onAttach).toHaveBeenCalledWith([file]);

  await userEvent.type(screen.getByPlaceholderText("输入问题，Enter 发送"), "看图{Enter}");
  expect(onSend).toHaveBeenCalledWith("看图", [], ["att1"]);
});

test("附件选择接受图片与常见文档类型", async () => {
  render(<Composer onSend={vi.fn()} onStop={vi.fn()} generating={false} />);
  const input = screen.getByTestId("attachment-input");
  expect(input).toHaveAttribute("type", "file");
  expect(input.getAttribute("accept")).toContain(".pdf");
  expect(input.getAttribute("accept")).toContain(".docx");
  expect(input.getAttribute("accept")).toContain(".md");
  expect(screen.getByRole("button", { name: "上传附件" })).toBeInTheDocument();
});

test("上传附件与发送/停止均为图标按钮（无可见文字）", () => {
  const { rerender } = render(<Composer onSend={vi.fn()} onStop={vi.fn()} generating={false} />);
  for (const name of ["上传附件", "发送"]) {
    const btn = screen.getByRole("button", { name });
    expect(btn.textContent).toBe("");
    expect(btn.querySelector("svg")).toBeInTheDocument();
  }
  rerender(<Composer onSend={vi.fn()} onStop={vi.fn()} generating={true} />);
  const stop = screen.getByRole("button", { name: "停止" });
  expect(stop.textContent).toBe("");
  expect(stop.querySelector("svg")).toBeInTheDocument();
});

test("文档 chip 显示文件名并可移除", async () => {
  const onRemoveAttachment = vi.fn();
  render(
    <Composer
      onSend={vi.fn()}
      onStop={vi.fn()}
      generating={false}
      attachments={[{ id: "doc1", name: "会议纪要.pdf", kind: "document" }]}
      onRemoveAttachment={onRemoveAttachment}
    />,
  );
  expect(screen.getByText("会议纪要.pdf")).toBeInTheDocument();
  expect(screen.queryByAltText("图片预览")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "移除附件" }));
  expect(onRemoveAttachment).toHaveBeenCalledWith("doc1");
});

test("附件达到 3 个后拒绝第 4 个并提示，发送最多 3 个 id", async () => {
  const onAttach = vi.fn();
  const onSend = vi.fn();
  render(
    <Composer
      onSend={onSend}
      onStop={vi.fn()}
      generating={false}
      attachments={[1, 2, 3].map((n) => ({ id: `att${n}`, previewUrl: `blob:${n}` }))}
      onAttach={onAttach}
    />,
  );
  await userEvent.upload(
    screen.getByTestId("attachment-input"),
    new File(["png"], "d.png", { type: "image/png" }),
  );
  expect(onAttach).not.toHaveBeenCalled();
  expect(await screen.findByText("最多上传 3 个附件")).toBeInTheDocument();

  await userEvent.type(screen.getByPlaceholderText("输入问题，Enter 发送"), "三张{Enter}");
  expect(onSend).toHaveBeenCalledWith("三张", [], ["att1", "att2", "att3"]);
});

test("sessionKey 变化时清空草稿与 @ 提及", async () => {
  const onSend = vi.fn();
  const { rerender } = render(
    <Composer onSend={onSend} onStop={vi.fn()} generating={false} agents={AGENTS} sessionKey="s1" />,
  );
  const input = () => screen.getByPlaceholderText("输入问题，Enter 发送") as HTMLInputElement;
  await userEvent.type(input(), "@深度");
  await userEvent.click(await screen.findByText("深度思考"));
  await userEvent.type(input(), " 跨会话草稿");
  expect(input().value).toContain("跨会话草稿");

  rerender(
    <Composer onSend={onSend} onStop={vi.fn()} generating={false} agents={AGENTS} sessionKey="s2" />,
  );
  expect(input().value).toBe("");
  // 旧 mentionIds 也必须丢弃：新会话发送不得携带 s1 的提及
  await userEvent.type(input(), "新会话{Enter}");
  expect(onSend).toHaveBeenCalledWith("新会话", [], []);
});

test("sessionKey 不变时保留草稿", async () => {
  const { rerender } = render(
    <Composer onSend={vi.fn()} onStop={vi.fn()} generating={false} sessionKey="s1" />,
  );
  const input = () => screen.getByPlaceholderText("输入问题，Enter 发送") as HTMLInputElement;
  await userEvent.type(input(), "半句草稿");
  rerender(<Composer onSend={vi.fn()} onStop={vi.fn()} generating={false} sessionKey="s1" />);
  expect(input().value).toBe("半句草稿");
});

test("输入框为多行 textarea，会话内与落地态高度递增", () => {
  const { rerender } = render(<Composer onSend={vi.fn()} onStop={vi.fn()} generating={false} />);
  const input = screen.getByPlaceholderText("输入问题，Enter 发送");
  expect(input.tagName).toBe("TEXTAREA");
  expect(input).toHaveClass("min-h-24");
  expect(input).toHaveClass("md:text-base");
  rerender(
    <Composer onSend={vi.fn()} onStop={vi.fn()} generating={false} variant="landing" />,
  );
  expect(screen.getByPlaceholderText("输入问题，Enter 发送")).toHaveClass("min-h-40");
});

const MODEL_OPTIONS = [
  { name: "qwen2.5:7b", size_mb: 4096 },
  { name: "llama3:8b", size_mb: null },
];

test("模型下拉选择后回调，未选时展示智能体默认并高亮当前项", async () => {
  const onModelChange = vi.fn();
  const { rerender } = render(
    <Composer
      onSend={vi.fn()}
      onStop={vi.fn()}
      generating={false}
      models={MODEL_OPTIONS}
      modelOverride={null}
      onModelChange={onModelChange}
      defaultModelLabel="qwen2.5:7b"
    />,
  );
  const trigger = () => screen.getByRole("button", { name: "选择模型" });
  expect(trigger()).toHaveTextContent("qwen2.5:7b");

  await userEvent.click(trigger());
  await userEvent.click(await screen.findByText("llama3:8b"));
  expect(onModelChange).toHaveBeenCalledWith("llama3:8b");

  rerender(
    <Composer
      onSend={vi.fn()}
      onStop={vi.fn()}
      generating={false}
      models={MODEL_OPTIONS}
      modelOverride="llama3:8b"
      onModelChange={onModelChange}
      defaultModelLabel="qwen2.5:7b"
    />,
  );
  expect(trigger()).toHaveTextContent("llama3:8b");
});

function dropFiles(files: File[]) {
  const zone = screen.getByTestId("composer-dropzone");
  const dataTransfer = { types: ["Files"], files };
  fireEvent.dragEnter(zone, { dataTransfer });
  return { zone, dataTransfer };
}

test("拖放文件到输入框：高亮提示并一次性上报多个文件", () => {
  const onAttach = vi.fn();
  render(<Composer onSend={vi.fn()} onStop={vi.fn()} generating={false} onAttach={onAttach} />);
  const files = [
    new File(["png"], "a.png", { type: "image/png" }),
    new File(["pdf"], "b.pdf", { type: "application/pdf" }),
  ];
  const { zone, dataTransfer } = dropFiles(files);
  expect(screen.getByText("松开即可上传附件")).toBeInTheDocument();

  fireEvent.drop(zone, { dataTransfer });
  expect(onAttach).toHaveBeenCalledWith(files);
  expect(screen.queryByText("松开即可上传附件")).not.toBeInTheDocument();
});

test("拖放不支持的文件类型被忽略并提示", () => {
  const onAttach = vi.fn();
  render(<Composer onSend={vi.fn()} onStop={vi.fn()} generating={false} onAttach={onAttach} />);
  const { zone, dataTransfer } = dropFiles([
    new File(["x"], "evil.exe", { type: "application/x-msdownload" }),
  ]);

  fireEvent.drop(zone, { dataTransfer });
  expect(onAttach).not.toHaveBeenCalled();
  expect(screen.getByText("已忽略 1 个不支持的文件")).toBeInTheDocument();
});

test("附件已满 3 个时拖放被拒绝并提示", () => {
  const onAttach = vi.fn();
  render(
    <Composer
      onSend={vi.fn()}
      onStop={vi.fn()}
      generating={false}
      attachments={[1, 2, 3].map((n) => ({ id: `att${n}` }))}
      onAttach={onAttach}
    />,
  );
  const { zone, dataTransfer } = dropFiles([
    new File(["png"], "d.png", { type: "image/png" }),
  ]);

  fireEvent.drop(zone, { dataTransfer });
  expect(onAttach).not.toHaveBeenCalled();
  expect(screen.getByText("最多上传 3 个附件")).toBeInTheDocument();
});

test("拖放数量超过剩余额度时按剩余额度截断并提示", () => {
  const onAttach = vi.fn();
  render(
    <Composer
      onSend={vi.fn()}
      onStop={vi.fn()}
      generating={false}
      attachments={[{ id: "att1" }, { id: "att2" }]}
      onAttach={onAttach}
    />,
  );
  const files = [
    new File(["png"], "a.png", { type: "image/png" }),
    new File(["png"], "b.png", { type: "image/png" }),
    new File(["png"], "c.png", { type: "image/png" }),
  ];
  const { zone, dataTransfer } = dropFiles(files);

  fireEvent.drop(zone, { dataTransfer });
  expect(onAttach).toHaveBeenCalledWith([files[0]]);
  expect(screen.getByText("最多上传 3 个附件")).toBeInTheDocument();
});
