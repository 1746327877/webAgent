import { mapPlainText } from "@/lib/plainText";

/**
 * 工具结果与正文里的 URL 白名单，与后端 `app/ai/runtime.py` 的 `_URL_SCHEME` 一一对应。
 * 单一来源在后端，改这里必须同步改后端；前端这层是渲染前的防御，
 * `javascript:` / `data:` / `file:` 一律不认，避免不可信数据变成可点击内容。
 */
const SCHEME = String.raw`https?://|weixin://|alipays?://|tel:|mailto:`;
/** 字符集与后端 `_URL_RE` 一致：排除引号/尖括号/括号/花括号与中文标点，避免吞掉 JSON 结构 */
const URL_BODY = String.raw`[^\s"'<>()\[\]{}，。；、]+`;
/** markdown 的 GFM 自动链接只认 http(s)/www/邮箱，这几类自定义协议要自己包 autolink */
const CUSTOM_SCHEME = String.raw`weixin://|alipays?://|tel:|mailto:`;
const TRAILING_PUNCT = /[.,;:!?，。；：！？]+$/;

// 带 g 的正则在 test/exec 之间共享 lastIndex，容易出隐蔽 bug，统一每次新建。
// 注意分支必须整体分组：`a|b|[^x]+` 的 `+` 只会作用在最后一个分支上
const schemeRe = () => new RegExp(`^(?:${SCHEME})`, "i");
const bareUrlRe = () => new RegExp(`(?:${SCHEME})${URL_BODY}`, "gi");
const bareCustomRe = () => new RegExp(`(?:${CUSTOM_SCHEME})${URL_BODY}`, "gi");

/** 剥掉粘在 URL 末尾的标点（工具返回常写作 "见 https://a.com。"） */
export function stripTrailingPunct(url: string): string {
  return url.replace(TRAILING_PUNCT, "");
}

/** 是否是白名单内的可点击 URL */
export function isClickableUrl(url: string): boolean {
  return typeof url === "string" && schemeRe().test(url);
}

/** 只有 http(s) 才能当 `<img src>` / 走浏览器外链加载 */
export function isHttpUrl(url: string): boolean {
  return /^https?:\/\//i.test(url);
}

export interface LinkSegment {
  kind: "text" | "link";
  value: string;
}

/**
 * 把纯文本切成「普通文本 / 可点击 URL」片段。
 *
 * 用于工具结果 preview 这类非 markdown 的纯文本：后端能提取到的 URL 只是结果里的
 * 一小部分，用户真正点到的往往是正文里那一个，所以渲染时也要能点。
 */
export function splitByLinks(text: string): LinkSegment[] {
  const segments: LinkSegment[] = [];
  let last = 0;
  for (const match of text.matchAll(bareUrlRe())) {
    const start = match.index ?? 0;
    const url = stripTrailingPunct(match[0]);
    if (!url) continue;
    if (start > last) segments.push({ kind: "text", value: text.slice(last, start) });
    segments.push({ kind: "link", value: url });
    // 被剥掉的标点留在后面的文本片段里
    last = start + url.length;
  }
  if (last < text.length) segments.push({ kind: "text", value: text.slice(last) });
  return segments;
}

/**
 * 把正文里的裸自定义协议 URL 包成 CommonMark autolink（`<weixin://…>`），
 * 让智能体直接写出来的支付链接也能点。http(s) 交给 remark-gfm，不在这里处理
 * （否则已有的 `<https://…>` 会被包成 `<<https://…>>` 反而坏掉）。
 */
export function autolinkBareUrls(content: string): string {
  return mapPlainText(content, (text) =>
    text.replace(bareCustomRe(), (match: string, offset: number, whole: string) => {
      const url = stripTrailingPunct(match);
      if (!url) return match;
      const tail = match.slice(url.length);
      const before = whole[offset - 1];
      const after = whole[offset + match.length];
      // 已经在 autolink `<url>` 或链接目标 `(url)` 里的不再包一层
      if ((before === "<" && after === ">") || (before === "(" && after === ")")) return match;
      return `<${url}>${tail}`;
    }),
  );
}
