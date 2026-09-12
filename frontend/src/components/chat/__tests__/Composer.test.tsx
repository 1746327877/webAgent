import { render, screen } from "@testing-library/react";
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
      attachments={[{ id: "att1", previewUrl: "blob:preview" }]}
      onAttach={onAttach}
      onRemoveAttachment={onRemoveAttachment}
    />,
  );
  expect(screen.getByAltText("图片预览")).toHaveAttribute("src", "blob:preview");
  await userEvent.click(screen.getByRole("button", { name: "移除图片" }));
  expect(onRemoveAttachment).toHaveBeenCalledWith("att1");

  const file = new File(["png"], "cat.png", { type: "image/png" });
  await userEvent.upload(screen.getByLabelText("选择图片"), file);
  expect(onAttach).toHaveBeenCalledWith(file);

  await userEvent.type(screen.getByPlaceholderText("输入问题，Enter 发送"), "看图{Enter}");
  expect(onSend).toHaveBeenCalledWith("看图", [], ["att1"]);
});

test("附件达到 3 张后拒绝第 4 张并提示，发送最多 3 个 id", async () => {
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
    screen.getByLabelText("选择图片"),
    new File(["png"], "d.png", { type: "image/png" }),
  );
  expect(onAttach).not.toHaveBeenCalled();
  expect(await screen.findByText("最多上传 3 张图片")).toBeInTheDocument();

  await userEvent.type(screen.getByPlaceholderText("输入问题，Enter 发送"), "三张{Enter}");
  expect(onSend).toHaveBeenCalledWith("三张", [], ["att1", "att2", "att3"]);
});
