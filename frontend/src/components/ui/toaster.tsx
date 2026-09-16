import { useEffect } from "react";
import { useToastStore, type ToastItem, type ToastVariant } from "@/stores/toast";
import { cn } from "cn";

const AUTO_DISMISS_MS: Record<ToastVariant, number> = {
  success: 3000,
  info: 3500,
  error: 6000,
};

const ICONS: Record<ToastVariant, string> = {
  success: "✅",
  error: "❌",
  info: "ℹ️",
};

function Toast({ item }: { item: ToastItem }) {
  const dismiss = useToastStore((s) => s.dismiss);

  useEffect(() => {
    const timer = window.setTimeout(() => dismiss(item.id), AUTO_DISMISS_MS[item.variant]);
    return () => window.clearTimeout(timer);
  }, [item.id, item.variant, dismiss]);

  return (
    <div
      role="status"
      data-variant={item.variant}
      className={cn(
        "pointer-events-auto flex w-80 items-start gap-2 rounded-lg border bg-background p-3 text-sm shadow-lg",
        item.variant === "success" && "border-primary/30",
        item.variant === "error" && "border-destructive/40",
      )}
    >
      <span aria-hidden>{ICONS[item.variant]}</span>
      <p className="min-w-0 flex-1 break-words">{item.message}</p>
      <button
        type="button"
        aria-label="关闭提示"
        className="shrink-0 text-muted-foreground hover:text-foreground"
        onClick={() => dismiss(item.id)}
      >
        ×
      </button>
    </div>
  );
}

export default function Toaster() {
  const toasts = useToastStore((s) => s.toasts);
  return (
    <div
      aria-live="polite"
      className="pointer-events-none fixed top-4 right-4 z-[100] flex max-h-[80vh] flex-col gap-2 overflow-hidden"
    >
      {toasts.map((item) => (
        <Toast key={item.id} item={item} />
      ))}
    </div>
  );
}
