import { useMcpServers } from "@/api/mcp";
import type { McpToolBinding } from "@/api/agents";
import { Badge } from "@/components/ui/badge";

const keyOf = (serverId: string, toolName: string) => `${serverId}:${toolName}`;

function statusText(status: string): string {
  if (status === "ok") return "连接正常";
  if (status === "error") return "连接失败";
  return "未测试";
}

export interface McpToolSelectorProps {
  value: McpToolBinding[];
  onChange: (tools: McpToolBinding[]) => void;
  disabled?: boolean;
}

/** 受控 MCP 工具选择器：server 名前的父复选框可整组全选；保存逻辑由外层负责。 */
export default function McpToolSelector({
  value,
  onChange,
  disabled = false,
}: McpToolSelectorProps) {
  const { data: servers = [], isLoading } = useMcpServers();
  const selected = new Set(value.map((b) => keyOf(b.mcp_server_id, b.tool_name)));

  const allKeys = servers.flatMap((server) =>
    server.tools.map((tool) => keyOf(server.id, tool.name)),
  );
  const allChecked = allKeys.length > 0 && allKeys.every((key) => selected.has(key));
  const someChecked = allKeys.some((key) => selected.has(key));

  function setKey(serverId: string, toolName: string, checked: boolean) {
    onChange(
      checked
        ? [...value, { mcp_server_id: serverId, tool_name: toolName }]
        : value.filter((b) => !(b.mcp_server_id === serverId && b.tool_name === toolName)),
    );
  }

  function setServer(serverId: string, toolNames: string[], checked: boolean) {
    const rest = value.filter((b) => b.mcp_server_id !== serverId);
    if (!checked) {
      onChange(rest);
      return;
    }
    const existing = new Set(rest.map((b) => keyOf(b.mcp_server_id, b.tool_name)));
    const added = toolNames
      .filter((name) => !existing.has(keyOf(serverId, name)))
      .map((name) => ({ mcp_server_id: serverId, tool_name: name }));
    onChange([...rest, ...added]);
  }

  if (isLoading) return <p className="text-sm text-muted-foreground">加载中…</p>;
  if (servers.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        还没有 MCP，请到「扩展能力 → MCP」新建并测试连接。
      </p>
    );
  }

  return (
    <div className="space-y-2">
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
            disabled={disabled}
            onChange={(e) =>
              onChange(
                e.target.checked
                  ? servers.flatMap((server) =>
                      server.tools.map((tool) => ({
                        mcp_server_id: server.id,
                        tool_name: tool.name,
                      })),
                    )
                  : [],
              )
            }
          />
          全选 / 清空（共 {allKeys.length} 个工具，已选 {value.length} 个）
        </label>
      )}

      {servers.map((server) => {
        const serverKeys = server.tools.map((tool) => keyOf(server.id, tool.name));
        const serverAll = serverKeys.length > 0 && serverKeys.every((k) => selected.has(k));
        const serverSome = serverKeys.some((k) => selected.has(k));
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
                disabled={disabled || server.tools.length === 0}
                onChange={(e) =>
                  setServer(
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
                {server.tools.map((tool) => (
                  <label key={tool.name} className="flex cursor-pointer items-start gap-2 text-sm">
                    <input
                      type="checkbox"
                      className="mt-0.5 size-4 shrink-0 accent-primary"
                      checked={selected.has(keyOf(server.id, tool.name))}
                      disabled={disabled}
                      onChange={(e) => setKey(server.id, tool.name, e.target.checked)}
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
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
