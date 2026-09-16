import { useState, type ComponentPropsWithoutRef, type ReactNode } from "react";
import Markdown, {
  defaultUrlTransform,
  type Components,
  type ExtraProps,
} from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";
import { linkifyCitations } from "@/lib/citations";
import { autolinkBareUrls, isClickableUrl } from "@/lib/linkify";
import UrlLink from "@/components/chat/UrlLink";
import { createHighlighterCoreSync } from "shiki/core";
import { createJavaScriptRegexEngine } from "shiki/engine/javascript";
import rehypeShikiFromHighlighter from "@shikijs/rehype/core";
import githubDark from "shiki/themes/github-dark.mjs";
import bash from "shiki/langs/bash.mjs";
import c from "shiki/langs/c.mjs";
import cpp from "shiki/langs/cpp.mjs";
import css from "shiki/langs/css.mjs";
import diff from "shiki/langs/diff.mjs";
import dockerfile from "shiki/langs/dockerfile.mjs";
import go from "shiki/langs/go.mjs";
import html from "shiki/langs/html.mjs";
import java from "shiki/langs/java.mjs";
import javascript from "shiki/langs/javascript.mjs";
import json from "shiki/langs/json.mjs";
import jsx from "shiki/langs/jsx.mjs";
import markdown from "shiki/langs/markdown.mjs";
import python from "shiki/langs/python.mjs";
import rust from "shiki/langs/rust.mjs";
import sql from "shiki/langs/sql.mjs";
import toml from "shiki/langs/toml.mjs";
import tsx from "shiki/langs/tsx.mjs";
import typescript from "shiki/langs/typescript.mjs";
import xml from "shiki/langs/xml.mjs";
import yaml from "shiki/langs/yaml.mjs";

// 同步 highlighter（非 async rehype 插件），保证 react-markdown 同步渲染不闪烁；
// 仅打包常用语言，未知语言降级为无高亮的原始代码块。
const highlighter = createHighlighterCoreSync({
  themes: [githubDark],
  langs: [
    bash, c, cpp, css, diff, dockerfile, go, html, java, javascript, json, jsx,
    markdown, python, rust, sql, toml, tsx, typescript, xml, yaml,
  ],
  engine: createJavaScriptRegexEngine(),
});

const rehypeShiki = () =>
  rehypeShikiFromHighlighter(highlighter, {
    theme: "github-dark",
    addLanguageClass: true,
    // 高亮失败时保留原始代码块，而不是让整条消息渲染失败
    onError: () => {},
  });

/** 递归提取 React 节点中的纯文本（shiki 高亮后为多层 span） */
function textContent(node: ReactNode): string {
  if (node == null || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textContent).join("");
  if (typeof node === "object" && "props" in node) {
    return textContent((node as { props?: { children?: ReactNode } }).props?.children);
  }
  return "";
}

/** 从 <pre> 的子 <code> 上读取 shiki 输出的 language-* 类 */
function languageOf(children: ReactNode): string | null {
  const child = Array.isArray(children) ? children[0] : children;
  if (child == null || typeof child !== "object" || !("props" in child)) return null;
  const className = (child as { props?: { className?: unknown } }).props?.className;
  const list = Array.isArray(className) ? className : typeof className === "string" ? className.split(" ") : [];
  const found = list.find((c) => typeof c === "string" && c.startsWith("language-"));
  return found ? found.slice("language-".length) : null;
}

function PreBlock({ children, node: _node, ...props }: ComponentPropsWithoutRef<"pre"> & ExtraProps) {
  const [copied, setCopied] = useState(false);
  const code = textContent(children);
  const language = languageOf(children);

  async function copy() {
    try {
      await navigator.clipboard?.writeText(code);
    } catch {
      // 剪贴板不可用（权限/非安全上下文）时降级：不中断渲染
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="my-2 overflow-hidden rounded-md border">
      <div className="flex items-center justify-between border-b bg-muted/50 px-2 py-1 text-xs text-muted-foreground">
        <span>{language ?? "code"}</span>
        <button type="button" className="transition-colors hover:text-foreground" onClick={copy}>
          {copied ? "已复制" : "复制"}
        </button>
      </div>
      <pre
        {...props}
        className={cn("overflow-x-auto p-3 text-sm", props.className)}
      >
        {children}
      </pre>
    </div>
  );
}

const CITATION_PREFIX = "#cite-";

/**
 * react-markdown 默认只放行 `https?|ircs?|mailto|xmpp`，会把 `weixin://` 这类支付链接
 * 的 href 清成空字符串（表现为「点了没反应」）。白名单内的协议原样保留，其余仍交给默认清理。
 */
function keepClickableSchemes(url: string): string {
  return isClickableUrl(url) ? url : defaultUrlTransform(url);
}

export default function MarkdownContent({
  content,
  maxRef = 0,
  onCitation,
}: {
  content: string;
  /** 本条消息 citation 的最大编号，只有存在的编号会转为 #cite-n 锚点 */
  maxRef?: number;
  onCitation?: (ref: number) => void;
}) {
  const components: Components = {
    pre: PreBlock,
    // 模型常把链接包在反引号里写成行内代码（`weixin://…`），而行内代码优先于自动链接解析，
    // 结果就是等宽文本、点不动（用户只会选中文字）。整段就是链接的行内代码直接渲染成链接。
    // 判定用「无语言标记 + 单行」：唯一的误伤是「无语言标记、内容只有一个 URL 的围栏代码块」，
    // 那种情况会显示成代码框里的链接，不影响使用。
    code: ({ node: _node, className, children, ...props }: ComponentPropsWithoutRef<"code"> & ExtraProps) => {
      const text = typeof children === "string" ? children : "";
      if (!className && !text.includes("\n") && isClickableUrl(text)) {
        return <UrlLink url={text} className="break-all text-primary underline" />;
      }
      return (
        <code className={className} {...props}>
          {children}
        </code>
      );
    },
    // 模型在回复里直接写 markdown 图片（工具给的二维码/生成图地址）时也能看到图
    img: ({ node: _node, ...props }: ComponentPropsWithoutRef<"img"> & ExtraProps) => (
      <a
        href={typeof props.src === "string" ? props.src : ""}
        target="_blank"
        rel="noreferrer noopener"
        title="在新标签页打开原图"
      >
        <img
          {...props}
          loading="lazy"
          className={cn("my-1 max-h-80 w-auto rounded-md border bg-white", props.className)}
        />
      </a>
    ),
    a: ({ node: _node, ...props }: ComponentPropsWithoutRef<"a"> & ExtraProps) => {
      const href = typeof props.href === "string" ? props.href : "";
      if (href.startsWith(CITATION_PREFIX)) {
        return (
          <a
            {...props}
            className={cn(
              "mx-0.5 rounded bg-muted px-1 align-super text-[0.7em] font-medium no-underline",
              props.className,
            )}
            onClick={(e) => {
              e.preventDefault();
              onCitation?.(Number(href.slice(CITATION_PREFIX.length)));
            }}
          />
        );
      }
      return <a {...props} />;
    },
  };
  return (
    <div className="prose prose-sm max-w-none dark:prose-invert">
      <Markdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeShiki]}
        components={components}
        urlTransform={keepClickableSchemes}
      >
        {autolinkBareUrls(linkifyCitations(content, maxRef))}
      </Markdown>
    </div>
  );
}
