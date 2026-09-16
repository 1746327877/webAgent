import { useState } from "react";
import { useDeleteMcpServer, useMcpServers, useTestMcpServer, type McpServer } from "@/api/mcp";
import McpForm from "@/components/capabilities/McpForm";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { toast } from "@/stores/toast";

function StatusBadge({ server }: { server: McpServer }) {
  if (server.status === "ok") return <Badge>连接正常</Badge>;
  if (server.status === "error") return <Badge variant="destructive">连接失败</Badge>;
  return <Badge variant="secondary">未测试</Badge>;
}

function endpoint(server: McpServer): string {
  if (server.transport === "http") return server.url ?? "";
  return [server.command, ...(server.args ?? [])].filter(Boolean).join(" ");
}

function checkedAt(server: McpServer): string {
  if (!server.last_checked_at) return "尚未测试";
  const date = new Date(server.last_checked_at);
  return `上次测试 ${Number.isNaN(date.getTime()) ? server.last_checked_at : date.toLocaleString()}`;
}

export default function McpPanel() {
  const { data, isLoading, error } = useMcpServers();
  const remove = useDeleteMcpServer();
  const test = useTestMcpServer();
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<McpServer | null>(null);

  const formOpen = creating || editing !== null;

  function closeForm() {
    setCreating(false);
    setEditing(null);
  }

  async function onTest(server: McpServer) {
    try {
      const result = await test.mutateAsync(server.id);
      if (result.ok) {
        toast.success(`${server.name}：连接成功（${result.latency_ms ?? 0}ms，${result.tools.length} 个工具）`);
      } else {
        toast.error(`${server.name}：${result.error ?? "连接失败"}`);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "测试连接失败");
    }
  }

  function onDelete(server: McpServer) {
    if (!window.confirm(`删除 MCP「${server.name}」？`)) return;
    remove.mutate(server.id, {
      onSuccess: () => toast.success(`已删除「${server.name}」`),
      onError: (err) => toast.error(err instanceof Error ? err.message : "删除失败"),
    });
  }

  return (
    <div className="space-y-3">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          MCP（Model Context Protocol）是外部工具服务。填好连接信息后点「测试连接」，
          会真实连上去并列出它提供的工具；保存后供智能体按 tool 粒度绑定。
        </p>
        <Button
          size="sm"
          className="shrink-0"
          disabled={formOpen}
          onClick={() => {
            setEditing(null);
            setCreating(true);
          }}
        >
          ＋ 新建 MCP
        </Button>
      </div>

      {formOpen && (
        <McpForm
          initial={editing}
          onSaved={() => {
            closeForm();
            toast.success("已保存");
          }}
          onCancel={closeForm}
        />
      )}

      {isLoading && <p className="text-sm text-muted-foreground">加载中…</p>}
      {error && <p className="text-sm text-red-500">{error.message}</p>}
      {!isLoading && !error && data?.length === 0 && !formOpen && (
        <p className="text-sm text-muted-foreground">还没有 MCP，点击右上角「新建 MCP」添加。</p>
      )}

      {data?.map((server) => (
        <Card key={server.id}>
          <CardContent className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{server.name}</span>
              <Badge variant="outline">{server.transport}</Badge>
              <StatusBadge server={server} />
              <span className="ml-auto text-xs text-muted-foreground">{checkedAt(server)}</span>
            </div>

            {endpoint(server) && (
              <p className="truncate font-mono text-xs text-muted-foreground">{endpoint(server)}</p>
            )}

            {server.last_error && <p className="text-xs text-red-500">{server.last_error}</p>}

            <details className="text-sm">
              <summary className="cursor-pointer text-xs text-muted-foreground">
                工具（{server.tools.length}）
              </summary>
              {server.tools.length === 0 ? (
                <p className="mt-1 text-xs text-muted-foreground">测试连接后可查看工具列表</p>
              ) : (
                <ul className="mt-1 space-y-0.5">
                  {server.tools.map((tool) => (
                    <li key={tool.name} className="text-xs text-muted-foreground">
                      <code className="text-foreground">{tool.name}</code>
                      {tool.description ? ` · ${tool.description}` : ""}
                    </li>
                  ))}
                </ul>
              )}
            </details>

            <div className="flex gap-2 pt-0.5">
              <Button
                size="sm"
                variant="outline"
                disabled={test.isPending}
                onClick={() => onTest(server)}
              >
                {test.isPending && test.variables === server.id ? "测试中…" : "测试连接"}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setCreating(false);
                  setEditing(server);
                }}
              >
                编辑
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="text-red-500"
                disabled={remove.isPending}
                onClick={() => onDelete(server)}
              >
                删除
              </Button>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
