import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import MessageItem from "@/components/chat/MessageItem";
import type { MessageItemData } from "@/api/sessions";

afterEach(() => {
  vi.unstubAllGlobals();
});

function makeMessage(overrides: Partial<MessageItemData> = {}): MessageItemData {
  return {
    id: "m1",
    role: "assistant",
    blocks: [{ type: "text", content: "部分回答" }],
    status: "done",
    rating: null,
    error: null,
    created_at: "2026-09-11T10:00:00Z",
    ...overrides,
  };
}

test("error 状态在内容下方显示失败提示", () => {
  render(<MessageItem message={makeMessage({ status: "error", error: "连接失败" })} />);
  expect(screen.getByText("部分回答")).toBeInTheDocument();
  expect(screen.getByText("生成失败，可点「重新生成」重试")).toBeInTheDocument();
});

test("stopped 状态显示已停止", () => {
  render(<MessageItem message={makeMessage({ status: "stopped" })} />);
  expect(screen.getByText("已停止")).toBeInTheDocument();
});

test("error 状态点击重试回调携带消息 id", async () => {
  const onRetry = vi.fn();
  render(
    <MessageItem message={makeMessage({ status: "error", error: "连接失败" })} onRetry={onRetry} />,
  );
  await userEvent.click(screen.getByRole("button", { name: "重试" }));
  expect(onRetry).toHaveBeenCalledWith("m1");
});

test("文档附件渲染文件名 chip，不请求 blob 也不渲染 img", () => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  render(
    <MessageItem
      message={makeMessage({
        role: "user",
        blocks: [{ type: "text", content: "看文档" }],
        attachments: [
          { id: "doc1", original_name: "会议纪要.pdf", kind: "document", size_bytes: 100 },
        ],
      })}
    />,
  );
  expect(screen.getByText("会议纪要.pdf")).toBeInTheDocument();
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
  expect(fetchMock).not.toHaveBeenCalled();
});

test("图片附件仍走鉴权 blob 渲染缩略图", async () => {
  const fetchMock = vi.fn(async () => new Response(new Blob(["img"]), { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  URL.createObjectURL = vi.fn(() => "blob:mock");
  URL.revokeObjectURL = vi.fn();
  render(
    <MessageItem
      message={makeMessage({
        role: "user",
        blocks: [{ type: "text", content: "看图" }],
        attachments: [{ id: "img1", original_name: "cat.png", kind: "image" }],
      })}
    />,
  );
  expect(await screen.findByAltText("附件图片")).toHaveAttribute("src", "blob:mock");
  expect(fetchMock).toHaveBeenCalledWith("/api/v1/attachments/img1", expect.anything());
});

test("工具返回的图片展示在回复下方（不在工具卡片折叠区里）", () => {
  render(
    <MessageItem
      message={makeMessage({
        blocks: [
          { type: "tool_call", id: "c1", tool: "lk_pay", args: "{}" },
          {
            type: "tool_result",
            id: "r1",
            tool: "lk_pay",
            status: "ok",
            preview: "订单已创建",
            images: ["https://open.lkcoffee.com/transfer/qrcode?token=abc"],
          },
          { type: "text", content: "好的！订单已创建，请扫码支付。" },
        ],
      })}
    />,
  );
  expect(screen.getByText("好的！订单已创建，请扫码支付。")).toBeInTheDocument();
  const img = screen.getByAltText("工具返回图片");
  expect(img).toHaveAttribute("src", "https://open.lkcoffee.com/transfer/qrcode?token=abc");
  // 工具卡片默认折叠，图片必须挂在回复正文这一层
  expect(img.closest("details")).toBeNull();
});

test("工具图片只保留 http(s) 且去重", () => {
  render(
    <MessageItem
      message={makeMessage({
        blocks: [
          {
            type: "tool_result",
            id: "r1",
            status: "ok",
            preview: "x",
            images: [
              "weixin://wxpay/bizpayurl?pr=abc.png",
              "javascript:alert(1)",
              "https://a.com/q.png",
              "https://a.com/q.png",
            ],
          },
        ],
      })}
    />,
  );
  expect(screen.getAllByAltText("工具返回图片")).toHaveLength(1);
  expect(screen.getByAltText("工具返回图片")).toHaveAttribute("src", "https://a.com/q.png");
});

test("引用卡片展示章节路径", () => {
  render(
    <MessageItem
      message={makeMessage({
        blocks: [
          { type: "text", content: "回答 [1]" },
          {
            type: "citation",
            ref: 1,
            chunk_id: "c1",
            source: "java.md",
            page: 12,
            score: 0.8,
            snippet: "片段",
            headings: ["第3章", "3.1 核心参数"],
          },
        ],
      })}
    />,
  );
  expect(screen.getByText(/第3章 › 3\.1 核心参数/)).toBeInTheDocument();
});

test("历史消息引用块没有 headings 时不渲染章节分隔符", () => {
  render(
    <MessageItem
      message={makeMessage({
        blocks: [
          { type: "text", content: "回答 [1]" },
          {
            type: "citation",
            ref: 1,
            chunk_id: "c1",
            source: "java.md",
            page: 12,
            score: 0.8,
            snippet: "片段",
          },
        ],
      })}
    />,
  );
  // 分块策略上线前的历史消息没有 headings 字段，兼容契约：只显示来源与页码，不出现 " › "
  expect(screen.getByText(/java\.md · p12/)).toBeInTheDocument();
  expect(screen.queryByText(/›/)).not.toBeInTheDocument();
});

test("用户消息显示附件名称，并渲染音频转写块", () => {
  render(
    <MessageItem
      message={makeMessage({
        role: "user",
        blocks: [
          { type: "text", content: "把这段语音转成文字" },
          { type: "transcript", name: "voice.wav", text: "线程池的核心参数", status: "ok" },
        ],
        attachments: [{ id: "a1", original_name: "voice.wav", kind: "audio", size_bytes: 100 }],
      })}
    />,
  );
  // 附件名以 chip 显示（音频走文档 chip 分支）
  expect(screen.getByText("voice.wav")).toBeInTheDocument();
  // 转写块此前在用户消息里完全没有渲染，这里必须可见
  expect(screen.getByText(/线程池的核心参数/)).toBeInTheDocument();
  expect(screen.getByText(/语音转写/)).toBeInTheDocument();
});

test("折叠框按内容宽度，不铺满整行", () => {
  render(
    <MessageItem
      message={makeMessage({
        role: "assistant",
        blocks: [{ type: "thinking", content: "想一下" }],
      })}
    />,
  );
  const details = screen.getByText("思考过程").closest("details");
  expect(details).toHaveClass("w-fit");
  expect(details).toHaveClass("max-w-full");
});

test("音频转写失败的块显示失败原因", () => {
  render(
    <MessageItem
      message={makeMessage({
        role: "user",
        blocks: [
          { type: "text", content: "转写一下" },
          {
            type: "transcript",
            name: "test.wav",
            text: "",
            status: "error",
            error: "语音转写 MCP 不可用",
          },
        ],
      })}
    />,
  );
  expect(screen.getByText(/语音转写 · test\.wav · 失败/)).toBeInTheDocument();
  expect(screen.getByText("语音转写 MCP 不可用")).toBeInTheDocument();
});

test("回复正文里已经写出的图片不重复展示", () => {
  const url = "https://a.com/q.png";
  render(
    <MessageItem
      message={makeMessage({
        blocks: [
          { type: "tool_result", id: "r1", status: "ok", preview: "x", images: [url] },
          { type: "text", content: `扫码支付：![二维码](${url})` },
        ],
      })}
    />,
  );
  // markdown 图片由正文渲染，下面不再重复来一份
  expect(screen.getByAltText("二维码")).toBeInTheDocument();
  expect(screen.queryByAltText("工具返回图片")).not.toBeInTheDocument();
});
