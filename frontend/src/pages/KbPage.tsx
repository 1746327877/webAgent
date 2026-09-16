import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useCreateKb, useDeleteKb, useKbs } from "@/api/kbs";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { toast } from "@/stores/toast";

export default function KbPage() {
  const { data: kbs, isLoading, error: loadError } = useKbs();
  const createKb = useCreateKb();
  const deleteKb = useDeleteKb();
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function onCreate() {
    const trimmed = name.trim();
    if (!trimmed) {
      setError("请输入知识库名称");
      return;
    }
    setError(null);
    try {
      const kb = await createKb.mutateAsync({
        name: trimmed,
        description: description.trim() || undefined,
      });
      setName("");
      setDescription("");
      setCreating(false);
      toast.success("知识库已创建");
      navigate(`/kb/${kb.id}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "创建失败");
    }
  }

  async function onDelete(id: string, kbName: string) {
    if (!window.confirm(`删除知识库「${kbName}」？其中的文档会一并删除。`)) return;
    try {
      await deleteKb.mutateAsync(id);
      toast.success("知识库已删除");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "删除失败");
    }
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto max-w-4xl space-y-4 p-6">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-semibold">知识库</h1>
          <Button onClick={() => setCreating((v) => !v)}>
            {creating ? "取消" : "＋ 新建知识库"}
          </Button>
        </div>

        {creating && (
          <Card>
            <CardContent className="space-y-2">
              <Input
                placeholder="知识库名称（必填，最多 64 字）"
                maxLength={64}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
              <Input
                placeholder="描述（可选）"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
              <div className="flex justify-end">
                <Button size="sm" onClick={onCreate} disabled={createKb.isPending}>
                  {createKb.isPending ? "创建中…" : "创建"}
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {error && <p className="text-sm text-red-500">{error}</p>}
        {loadError && <p className="text-sm text-red-500">{loadError.message}</p>}
        {isLoading && <p className="text-sm text-muted-foreground">加载中…</p>}
        {!isLoading && !loadError && kbs?.length === 0 && (
          <p className="text-sm text-muted-foreground">还没有知识库，点击右上角「新建知识库」开始。</p>
        )}

        <div className="grid gap-3 sm:grid-cols-2">
          {kbs?.map((kb) => (
            <Card key={kb.id} className="h-full transition-colors hover:bg-accent/40">
              <CardContent className="flex items-start gap-3">
                <Link to={`/kb/${kb.id}`} className="min-w-0 flex-1">
                  <p className="truncate font-medium">📚 {kb.name}</p>
                  <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">
                    {kb.description || "暂无描述"}
                  </p>
                  <p className="mt-2 text-xs text-muted-foreground">
                    {kb.embedding_model} · 分块 {kb.chunk_size}/{kb.chunk_overlap}
                  </p>
                </Link>
                <Button
                  variant="ghost"
                  size="sm"
                  className="shrink-0 text-red-500"
                  disabled={deleteKb.isPending}
                  onClick={() => onDelete(kb.id, kb.name)}
                >
                  删除
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}
