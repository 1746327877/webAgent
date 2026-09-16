import type { ReactNode } from "react";
import { cn } from "cn";

export interface TabItem {
  key: string;
  label: string;
}

/**
 * 轻量标签页（手写，不引依赖）。面板由调用方按 value 条件渲染，
 * 每次切换重新挂载 → 进入动画自然重放；不做离场动画，避免布局抖动。
 */
export function Tabs({
  value,
  onChange,
  items,
  ariaLabel,
  className,
}: {
  value: string;
  onChange: (key: string) => void;
  items: readonly TabItem[];
  ariaLabel?: string;
  className?: string;
}) {
  return (
    <div role="tablist" aria-label={ariaLabel} className={cn("flex gap-1 border-b", className)}>
      {items.map((item) => {
        const active = item.key === value;
        return (
          <button
            key={item.key}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(item.key)}
            className={cn(
              "relative rounded-t px-3 py-1.5 text-sm transition-colors",
              active
                ? "font-medium text-foreground"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {item.label}
            {active && (
              <span className="absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-primary" />
            )}
          </button>
        );
      })}
    </div>
  );
}

/** 标签页内容容器：淡入 + 轻微上滑，尊重 prefers-reduced-motion。 */
export function TabsPanel({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        "animate-in fade-in-0 slide-in-from-bottom-1 duration-200 ease-out motion-reduce:animate-none",
        className,
      )}
    >
      {children}
    </div>
  );
}
