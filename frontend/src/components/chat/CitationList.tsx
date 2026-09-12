import type { Citation } from "@/lib/citations";

/** 「回答依据」折叠区：每项 [n] 来源 · pN（score），点击回调打开引用抽屉 */
export default function CitationList({
  citations,
  onOpen,
}: {
  citations: Citation[];
  onOpen?: (citation: Citation) => void;
}) {
  if (citations.length === 0) return null;
  return (
    <details open className="mb-1 rounded border px-3 py-2 text-sm">
      <summary className="cursor-pointer text-muted-foreground">
        回答依据（{citations.length}）
      </summary>
      <ul className="mt-1 space-y-0.5">
        {citations.map((c) => (
          <li key={c.ref}>
            <button
              type="button"
              className="text-left hover:text-foreground hover:underline"
              onClick={() => onOpen?.(c)}
            >
              [{c.ref}] {c.source}
              {c.page != null ? ` · p${c.page}` : ""}（{c.score.toFixed(2)}）
            </button>
          </li>
        ))}
      </ul>
    </details>
  );
}
