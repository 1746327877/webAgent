import { useState } from "react";
import { useAgentVersions, useRollbackAgent } from "@/api/agents";
import { Button } from "@/components/ui/button";

export interface VersionsDrawerProps {
  agentId: string;
  open: boolean;
  onClose: () => void;
}

export default function VersionsDrawer({ agentId, open, onClose }: VersionsDrawerProps) {
  const { data: versions, isLoading, error } = useAgentVersions(open ? agentId : undefined);
  const rollback = useRollbackAgent();
  const [notice, setNotice] = useState<string | null>(null);
  const [rollbackError, setRollbackError] = useState<string | null>(null);

  if (!open) return null;

  async function onRollback(version: number) {
    if (!window.confirm(`回滚到 v${version}？当前编辑内容将被该版本覆盖。`)) return;
    setNotice(null);
    setRollbackError(null);
    try {
      await rollback.mutateAsync({ id: agentId, version });
      setNotice(`已回滚到 v${version}`);
    } catch (err) {
      setRollbackError(err instanceof Error ? err.message : "回滚失败");
    }
  }

  return (
    <div
      role="dialog"
      aria-label="版本历史"
      className="fixed inset-0 z-50 flex justify-end bg-black/30"
      onClick={onClose}
    >
      <div
        className="h-full w-full max-w-md overflow-y-auto bg-background p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">版本历史</h2>
          <Button variant="ghost" size="sm" onClick={onClose}>关闭</Button>
        </div>

        {notice && <p className="mt-3 text-sm text-green-600">{notice}</p>}
        {rollbackError && <p className="mt-3 text-sm text-red-500">{rollbackError}</p>}
        {isLoading && <p className="mt-3 text-sm text-muted-foreground">加载中…</p>}
        {error && <p className="mt-3 text-sm text-red-500">{error.message}</p>}

        <div className="mt-4 space-y-3">
          {versions?.map((v) => (
            <div key={v.version} className="rounded-lg border border-border p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-medium">v{v.version}</span>
                <span className="text-xs text-muted-foreground">
                  {new Date(v.created_at).toLocaleString()}
                </span>
              </div>
              <p className="mt-1 truncate text-sm text-muted-foreground">
                {String(v.snapshot.name ?? "")}
              </p>
              <Button
                className="mt-2"
                size="sm"
                variant="outline"
                disabled={rollback.isPending}
                onClick={() => onRollback(v.version)}
              >
                回滚到此版本
              </Button>
            </div>
          ))}
          {!isLoading && !error && versions?.length === 0 && (
            <p className="text-sm text-muted-foreground">还没有发布版本。</p>
          )}
        </div>
      </div>
    </div>
  );
}
