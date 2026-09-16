import { useState } from "react";
import { useSetAgentMcpTools, type AgentItem, type McpToolBinding } from "@/api/agents";
import { useMcpServers } from "@/api/mcp";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

function statusText(status: string): string {
  if (status === "ok") return "连接正常";
  if (status === "error") return "连接失败";
  return "未测试";
}

export default function McpBindings({
  agent,
  onNotice,
  onError,
}: {
  agent: AgentItem;
  onNotice: (message: string) => void;
  onError: (message: string) => void;
}) {
  const { data: servers = [], isLoading } = useMcpServers();
  const setTools = useSetAgentMcpTools();
  const initial = agent.mcp_tools ?? [];
  const [draft, setDraft] = useState<McpToolBinding[]>(initial);

  const keyOf = (serverId: string, toolName: string) => `${serverId}:${toolName}`;
  const initialKeys = new Set(initial.map((b) => keyOf(b.mcp_server_id, b.tool_name)));
  const draftKeys = new Set(draft.map((b) => keyOf(b.mcp_server_id, b.tool_name)));
  const dirty =
    draftKeys.size !== initialKeys.size || [...draftKeys].some((key) => !initialKeys.has(key));

  // 全部可绑定工具（用于"全选所有"）
  const allKeys = servers.flatMap((server) =>
    server.tools.map((tool) => keyOf(server.id, tool.name)),
  );
  const allChecked = allKeys.length > 0 && allKeys.every((key) => draftKeys.has(key));
  const someChecked = allKeys.some((key) => draftKeys.has(key));

  function toggle(serverId: string, toolName: string, checked: boolean) {
    setDraft((prev) =>
      checked
        ? [...prev, { mcp_server_id: serverId, tool_name: toolName }]
        : prev.filter((b) => !(b.mcp_server_id === serverId && b.tool_name === toolName)),
    );
  }

  /** 父级：勾选=全选该 server 下全部 tool；取消=清空该 server */
  function toggleServer(serverId: string, toolNames: string[], checked: boolean) {
    setDraft((prev) => {
      const rest = prev.filter((b) => b.mcp_server_id !== serverId);
      if (!checked) return rest;
      const existing = new Set(rest.map((b) => keyOf(b.mcp_server_id, b.tool_name)));
      const added = toolNames
        .filter((name) => !existing.has(keyOf(serverId, name)))
        .map((name) => ({ mcp_server_id: serverId, tool_name: name }));
      return [...rest, ...added];
    });
  }

  function toggleAll(checked: boolean) {
    setDraft(
      checked
        ? servers.flatMap((server) =>
            server.tools.map((tool) => ({ mcp_server_id: server.id, tool_name: tool.name })),
          )
        : [],
    );
  }

  async function onSave() {
    try {
      const res = await setTools.mutateAsync({ id: agent.id, tools: draft });
      setDraft(res.tools ?? []);
      onNotice("MCP 工具绑定已保存");
    } catch (err) {
      onError(err instanceof Error ? err.message : "保存 MCP 绑定失败");
    }
  }

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-medium">MCP 工具绑定</h2>
          <p className="text-xs text-muted-foreground">
            勾选 server 名前的父复选框可一次全选该 server 的全部工具。
          </p>
        </div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={setTools.isPending || !dirty}
          onClick={onSave}
        >
          {setTools.isPending ? "保存中…" : "保存 MCP 绑定"}
        </Button>
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">加载中…</p>}
      {!isLoading && servers.length === 0 && (
        <p className="text-sm text-muted-foreground">
          还没有 MCP，请到「扩展能力 → MCP」新建并测试连接。
        </p>
      )}

      {allKeys.length > 0 && (
        <label className="flex cursor-pointer items-center gap-2 text-xs text-muted-foreground">
          <input
            type="checkbox"
            aria-label="全选 MCP 工具"
            className="size-4 shrink-0 accent-primary"
            checked={allChecked}
            ref={(el) => {
              if (el) el.indeterminate = someChecked && !allChecked;
            }}
            disabled={setTools.isPending}
            onChange={(e) => toggleAll(e.target.checked)}
          />
          全选 / 清空（共 {allKeys.length} 个工具，已选 {draft.length} 个）
        </label>
      )}

      <div className="space-y-2">
        {servers.map((server) => {
          const serverKeys = server.tools.map((tool) => keyOf(server.id, tool.name));
          const serverAll = serverKeys.length > 0 && serverKeys.every((k) => draftKeys.has(k));
          const serverSome = serverKeys.some((k) => draftKeys.has(k));
          return (
            <div key={server.id} className="rounded-lg border p-3">
              <div className="flex flex-wrap items-center gap-2">
                <input
                  type="checkbox"
                  aria-label={`全选 ${server.name}`}
                  className="size-4 shrink-0 accent-primary"
                  checked={serverAll}
                  ref={(el) => {
                    if (el) el.indeterminate = serverSome && !serverAll;
                  }}
                  disabled={setTools.isPending || server.tools.length === 0}
                  onChange={(e) =>
                    toggleServer(
                      server.id,
                      server.tools.map((tool) => tool.name),
                      e.target.checked,
                    )
                  }
                />
                <span className="text-sm font-medium">{server.name}</span>
                <Badge variant="outline">{server.transport}</Badge>
                <Badge variant={server.status === "ok" ? "default" : "secondary"}>
                  {statusText(server.status)}
                </Badge>
                {server.tools.length > 0 && (
                  <span className="text-xs text-muted-foreground">{server.tools.length} 个工具</span>
                )}
              </div>
              {server.tools.length === 0 ? (
                <p className="mt-1 text-xs text-muted-foreground">
                  还没有工具列表，请先到「扩展能力 → MCP」测试连接。
                </p>
              ) : (
                <div className="mt-2 space-y-1">
                  {server.tools.map((tool) => {
                    const checked = draftKeys.has(keyOf(server.id, tool.name));
                    return (
                      <label
                        key={tool.name}
                        className="flex cursor-pointer items-start gap-2 text-sm"
                      >
                        <input
                          type="checkbox"
                          className="mt-0.5 size-4 shrink-0 accent-primary"
                          checked={checked}
                          disabled={setTools.isPending}
                          onChange={(e) => toggle(server.id, tool.name, e.target.checked)}
                        />
                        <span className="min-w-0">
                          <code className="text-xs">{tool.name}</code>
                          {tool.description ? (
                            <span className="ml-2 text-xs text-muted-foreground">
                              {tool.description}
                            </span>
                          ) : null}
                        </span>
                      </label>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
