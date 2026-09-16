import { useState } from "react";
import { useSetAgentTools, type AgentItem, type ToolInfo } from "@/api/agents";
import McpBindings from "@/components/agents/McpBindings";
import SkillBindings from "@/components/agents/SkillBindings";
import ToolsMatrix from "@/components/agents/ToolsMatrix";
import { Button } from "@/components/ui/button";
import { Tabs, TabsPanel } from "@/components/ui/tabs";

const TABS = [
  { key: "skill", label: "Skill" },
  { key: "mcp", label: "MCP" },
  { key: "tool", label: "Tool" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

/** 内置工具绑定（沿用 ToolsMatrix，带全选/清空） */
function ToolBindings({
  agent,
  tools,
  onNotice,
  onError,
}: {
  agent: AgentItem;
  tools: ToolInfo[];
  onNotice: (message: string) => void;
  onError: (message: string) => void;
}) {
  const initial = agent.tool_slugs ?? [];
  const setTools = useSetAgentTools();
  const [draft, setDraft] = useState<string[]>(initial);
  const dirty = [...draft].sort().join(",") !== [...initial].sort().join(",");

  async function onSave() {
    try {
      const res = await setTools.mutateAsync({ id: agent.id, slugs: draft });
      setDraft(res.slugs ?? []);
      onNotice("工具绑定已保存");
    } catch (err) {
      onError(err instanceof Error ? err.message : "保存工具绑定失败");
    }
  }

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-medium">内置工具绑定</h2>
          <p className="text-xs text-muted-foreground">勾选后模型可在对话中调用这些内置工具。</p>
        </div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={setTools.isPending || !dirty}
          onClick={onSave}
        >
          {setTools.isPending ? "保存中…" : "保存工具绑定"}
        </Button>
      </div>
      <ToolsMatrix tools={tools} value={draft} onChange={setDraft} disabled={setTools.isPending} />
    </section>
  );
}

/** 智能体「扩展能力」：Skill / MCP / Tool 用子标签切换，避免长滚动。 */
export default function CapabilityBindings({
  agent,
  tools,
  onNotice,
  onError,
}: {
  agent: AgentItem;
  tools: ToolInfo[];
  onNotice: (message: string) => void;
  onError: (message: string) => void;
}) {
  const [tab, setTab] = useState<TabKey>("skill");

  return (
    <div className="space-y-4">
      <Tabs
        value={tab}
        onChange={(key) => setTab(key as TabKey)}
        items={TABS}
        ariaLabel="扩展能力分类"
      />
      {tab === "skill" && (
        <TabsPanel>
          <SkillBindings agent={agent} onNotice={onNotice} onError={onError} />
        </TabsPanel>
      )}
      {tab === "mcp" && (
        <TabsPanel>
          <McpBindings agent={agent} onNotice={onNotice} onError={onError} />
        </TabsPanel>
      )}
      {tab === "tool" && (
        <TabsPanel>
          <ToolBindings
            agent={agent}
            tools={tools}
            onNotice={onNotice}
            onError={onError}
          />
        </TabsPanel>
      )}
    </div>
  );
}
