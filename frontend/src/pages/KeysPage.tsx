import { useState } from "react";
import { useApiKeys, useCreateApiKey, useRevokeApiKey } from "@/api/keys";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

export default function KeysPage() {
  const { data: keys = [], isLoading, error } = useApiKeys();
  const createKey = useCreateApiKey();
  const revokeKey = useRevokeApiKey();
  const [name, setName] = useState("");
  const [created, setCreated] = useState<string | null>(null);

  async function onCreate() {
    if (!name.trim()) return;
    const key = await createKey.mutateAsync(name.trim());
    setCreated(key.key);
    setName("");
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto max-w-3xl space-y-4 p-6">
        <h1 className="text-xl font-semibold">🔑 API 密钥</h1>
        <p className="text-sm text-muted-foreground">
          OpenAI 兼容端点：<code>POST /v1/chat/completions</code>，model 传{" "}
          <code>agent:&lt;智能体 id&gt;</code>，用 <code>Authorization: Bearer sk-…</code> 调用。
        </p>
        <Card>
          <CardContent className="flex gap-2 pt-4">
            <Input
              aria-label="密钥名称"
              placeholder="密钥名称（如：本地脚本）"
              value={name}
              maxLength={64}
              onChange={(e) => setName(e.target.value)}
            />
            <Button onClick={onCreate} disabled={createKey.isPending}>
              创建
            </Button>
          </CardContent>
        </Card>
        {created && (
          <Card>
            <CardContent className="space-y-2 pt-4">
              <p className="text-sm text-amber-600">明文仅此一次展示，请立即复制保存。</p>
              <code className="block break-all rounded bg-muted p-2 text-xs">{created}</code>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  navigator.clipboard?.writeText(created);
                }}
              >
                复制
              </Button>
            </CardContent>
          </Card>
        )}
        {isLoading && <p className="text-sm text-muted-foreground">加载中…</p>}
        {error && <p className="text-sm text-red-500">{error.message}</p>}
        <div className="space-y-2">
          {keys.map((key) => (
            <div key={key.id} className="flex items-center gap-2 rounded border p-2 text-sm">
              <span className="font-medium">{key.name}</span>
              <code className="text-xs text-muted-foreground">{key.key_prefix}…</code>
              {key.revoked ? (
                <span className="ml-auto text-xs text-muted-foreground">已吊销</span>
              ) : (
                <Button
                  variant="ghost"
                  size="sm"
                  className="ml-auto text-red-500"
                  onClick={() => {
                    if (window.confirm("吊销该密钥？")) revokeKey.mutate(key.id);
                  }}
                >
                  吊销
                </Button>
              )}
            </div>
          ))}
          {!isLoading && keys.length === 0 && (
            <p className="text-sm text-muted-foreground">还没有密钥，先创建一个。</p>
          )}
        </div>
      </div>
    </div>
  );
}
