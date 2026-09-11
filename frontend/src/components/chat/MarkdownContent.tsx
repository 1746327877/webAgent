import { useState, type ComponentPropsWithoutRef, type ReactNode } from "react";
import Markdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
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

function PreBlock({ children }: ComponentPropsWithoutRef<"pre">) {
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
      <pre className="overflow-x-auto p-3 text-sm">{children}</pre>
    </div>
  );
}

const components: Components = { pre: PreBlock };

export default function MarkdownContent({ content }: { content: string }) {
  return (
    <div className="prose prose-sm max-w-none dark:prose-invert">
      <Markdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeShiki]} components={components}>
        {content}
      </Markdown>
    </div>
  );
}
