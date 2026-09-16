import type { ReactNode } from "react";
import { isHttpUrl } from "@/lib/linkify";

/**
 * 白名单内的 URL 链接（判定见 `lib/linkify`）。
 *
 * `http(s)` 走新标签页；自定义协议（`weixin://` 等）**不加 `target`**，
 * 直接交给系统协议处理器唤起客户端——加了反而可能先弹一个空白标签页。
 */
export default function UrlLink({
  url,
  children,
  className,
}: {
  url: string;
  children?: ReactNode;
  className?: string;
}) {
  const external = isHttpUrl(url);
  return (
    <a
      href={url}
      {...(external ? { target: "_blank", rel: "noreferrer noopener" } : {})}
      title={external ? `${url}（Ctrl/⌘+点击在新标签页打开）` : `${url}（点击唤起对应客户端）`}
      className={className}
    >
      {children ?? url}
    </a>
  );
}
