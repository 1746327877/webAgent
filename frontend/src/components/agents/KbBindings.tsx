import { useState } from "react";
import { useSetAgentKbs, type KbBinding } from "@/api/agents";
import { useKbs } from "@/api/kbs";
import { Button } from "@/components/ui/button";

export interface KbBindingsProps {
  agentId: string;
  bindings: KbBinding[];
  editable?: boolean;
  onNotice?: (message: string) => void;
  onError?: (message: string) => void;
}

interface DraftBinding {
  kb_id: string;
  top_k: number;
}

function toDraft(bindings: KbBinding[]): DraftBinding[] {
  return bindings.map((b) => ({ kb_id: b.kb_id, top_k: b.top_k }));
}

function sortKey(bindings: { kb_id: string; top_k: number }[]): string {
  return [...bindings]
    .map((b) => `${b.kb_id}:${b.top_k}`)
    .sort()
    .join(",");
}

export default function KbBindings({
  agentId,
  bindings,
  editable = true,
  onNotice,
  onError,
}: KbBindingsProps) {
  const { data: kbs } = useKbs();
  const setKbs = useSetAgentKbs();
  const [draft, setDraft] = useState<DraftBinding[]>(() => toDraft(bindings));
  const [saved, setSaved] = useState<DraftBinding[]>(() => toDraft(bindings));
  const dirty = sortKey(draft) !== sortKey(saved);
  const pending = setKbs.isPending;

  function toggle(kbId: string, checked: boolean) {
    setDraft((prev) =>
      checked
        ? [...prev.filter((b) => b.kb_id !== kbId), { kb_id: kbId, top_k: 5 }]
        : prev.filter((b) => b.kb_id !== kbId),
    );
  }

  function setTopK(kbId: string, topK: number) {
    setDraft((prev) => prev.map((b) => (b.kb_id === kbId ? { ...b, top_k: topK } : b)));
  }

  async function onSave() {
    try {
      const res = await setKbs.mutateAsync({ agentId, bindings: draft });
      const next = toDraft(res.bindings ?? []);
      setSaved(next);
      setDraft(next);
      onNotice?.("知识库绑定已保存");
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "保存知识库绑定失败");
    }
  }

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-medium">知识库绑定</h2>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={!editable || pending || !dirty}
          onClick={onSave}
        >
          {pending ? "保存中…" : "保存知识库绑定"}
        </Button>
      </div>
      {!kbs || kbs.length === 0 ? (
        <p className="text-sm text-muted-foreground">暂无可绑定的知识库。</p>
      ) : (
        <div className="space-y-2">
          {kbs.map((kb) => {
            const bound = draft.find((b) => b.kb_id === kb.id);
            return (
              <div
                key={kb.id}
                className="flex items-center gap-3 rounded-lg border border-border p-3"
              >
                <input
                  id={`kb-${kb.id}`}
                  type="checkbox"
                  className="size-4 shrink-0 accent-primary"
                  checked={Boolean(bound)}
                  disabled={!editable || pending}
                  onChange={(e) => toggle(kb.id, e.target.checked)}
                />
                <label
                  htmlFor={`kb-${kb.id}`}
                  className="min-w-0 flex-1 cursor-pointer text-sm font-medium"
                >
                  {kb.name}
                </label>
                {bound && (
                  <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    top_k
                    <input
                      type="number"
                      min={1}
                      max={20}
                      className="w-16 rounded-md border border-border bg-transparent px-2 py-1 text-sm"
                      value={bound.top_k}
                      disabled={!editable || pending}
                      aria-label={`${kb.name} top_k`}
                      onChange={(e) => setTopK(kb.id, Number(e.target.value))}
                    />
                  </label>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
