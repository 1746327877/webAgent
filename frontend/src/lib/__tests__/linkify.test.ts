import { expect, test } from "vitest";
import { autolinkBareUrls, isClickableUrl, isHttpUrl, splitByLinks } from "@/lib/linkify";

test("splitByLinks 切出文本与 URL 片段", () => {
  const segments = splitByLinks("点击支付链接：weixin://wxpay/bizpayurl?pr=abc 完成");
  expect(segments).toEqual([
    { kind: "text", value: "点击支付链接：" },
    { kind: "link", value: "weixin://wxpay/bizpayurl?pr=abc" },
    { kind: "text", value: " 完成" },
  ]);
});

test("splitByLinks 剥掉粘在 URL 末尾的标点", () => {
  const segments = splitByLinks("见 https://a.com/x。");
  expect(segments).toEqual([
    { kind: "text", value: "见 " },
    { kind: "link", value: "https://a.com/x" },
    { kind: "text", value: "。" },
  ]);
});

test("splitByLinks 无 URL 时原样返回", () => {
  expect(splitByLinks("没有链接")).toEqual([{ kind: "text", value: "没有链接" }]);
});

test("白名单外的 scheme 不可点击", () => {
  expect(isClickableUrl("javascript:alert(1)")).toBe(false);
  expect(isClickableUrl("data:image/png;base64,AAAA")).toBe(false);
  expect(isClickableUrl("file:///C:/x")).toBe(false);
  expect(isClickableUrl("/relative/path")).toBe(false);
  expect(isClickableUrl("weixin://wxpay/bizpayurl?pr=abc")).toBe(true);
  expect(isClickableUrl("https://a.com")).toBe(true);
  expect(isClickableUrl("mailto:a@b.com")).toBe(true);
});

test("只有 http(s) 能当图片地址", () => {
  expect(isHttpUrl("https://a.com/t.png")).toBe(true);
  expect(isHttpUrl("weixin://wxpay/bizpayurl?pr=abc.png")).toBe(false);
});

test("正文里的裸自定义协议包成 autolink", () => {
  const out = autolinkBareUrls("点击支付链接：weixin://wxpay/bizpayurl?pr=abc 或扫码");
  expect(out).toContain("<weixin://wxpay/bizpayurl?pr=abc>");
  expect(out).toContain("点击支付链接：");
});

test("http(s) 交给 remark-gfm，不在这里包（避免 <url> 变 <<url>>）", () => {
  expect(autolinkBareUrls("见 https://a.com/x")).toBe("见 https://a.com/x");
  expect(autolinkBareUrls("见 <https://a.com/x>")).toBe("见 <https://a.com/x>");
});

test("已是 autolink 或链接目标的 URL 不重复包", () => {
  expect(autolinkBareUrls("<weixin://wxpay?pr=abc>")).toBe("<weixin://wxpay?pr=abc>");
  expect(autolinkBareUrls("[付](weixin://wxpay?pr=abc)")).toBe("[付](weixin://wxpay?pr=abc)");
});

test("围栏代码块与行内代码里的链接不转换", () => {
  const fenced = autolinkBareUrls("示例：\n```\nweixin://wxpay?pr=abc\n```\n结论");
  expect(fenced).toContain("```\nweixin://wxpay?pr=abc\n```");
  expect(fenced).not.toContain("<weixin://wxpay?pr=abc>");

  const inline = autolinkBareUrls("例如 `weixin://wxpay?pr=abc` 这样");
  expect(inline).toBe("例如 `weixin://wxpay?pr=abc` 这样");
});
