import { useState } from "react";
import { useSetAgentMcpTools, type AgentItem, type McpToolBinding } from "@/api/agents";
import McpToolSelector from "@/components/agents/McpToolSelector";
import { Button } from "@/components/ui/button";

export default function McpBindings({
  agent,
  onNotice,
  onError,
}: {
  agent: AgentItem;
  onNotice: (message: string) => void;
  onError: (message: string) => void;
}) {
  const initial = agent.mcp_tools ?? [];
  const [draft, setDraft] = useState<McpToolBinding[]>(initial);
  const setTools = useSetAgentMcpTools();

  const keyOf = (b: McpToolBinding) => `${b.mcp_server_id}:${b.tool_name}`;
  const initialKeys = new Set(initial.map(keyOf));
  const draftKeys = new Set(draft.map(keyOf));
  const dirty =
    draftKeys.size !== initialKeys.size || [...draftKeys].some((key) => !initialKeys.has(key));

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
      <McpToolSelector value={draft} onChange={setDraft} disabled={setTools.isPending} />
    </section>
  );
}
