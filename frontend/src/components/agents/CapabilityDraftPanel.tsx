import { useState } from "react";
import type { McpToolBinding, ToolInfo } from "@/api/agents";
import McpToolSelector from "@/components/agents/McpToolSelector";
import SkillSelector from "@/components/agents/SkillSelector";
import ToolsMatrix from "@/components/agents/ToolsMatrix";
import { Tabs, TabsPanel } from "@/components/ui/tabs";

const TABS = [
  { key: "skill", label: "Skill" },
  { key: "mcp", label: "MCP" },
  { key: "tool", label: "Tool" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

export interface CapabilityDraft {
  skillSlugs: string[];
  toolSlugs: string[];
  mcpTools: McpToolBinding[];
}

/** 新建智能体时的扩展能力草稿面板：只收集选择，保存交给创建成功后的串联请求。 */
export default function CapabilityDraftPanel({
  tools,
  draft,
  onChange,
  disabled = false,
}: {
  tools: ToolInfo[];
  draft: CapabilityDraft;
  onChange: (patch: Partial<CapabilityDraft>) => void;
  disabled?: boolean;
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
          <p className="mb-2 text-xs text-muted-foreground">
            绑定的 Skill 会把指令注入 system prompt；创建智能体后生效。
          </p>
          <SkillSelector
            value={draft.skillSlugs}
            onChange={(skillSlugs) => onChange({ skillSlugs })}
            disabled={disabled}
          />
        </TabsPanel>
      )}
      {tab === "mcp" && (
        <TabsPanel>
          <p className="mb-2 text-xs text-muted-foreground">
            可精确选择某个 MCP 下的工具；创建智能体后生效。
          </p>
          <McpToolSelector
            value={draft.mcpTools}
            onChange={(mcpTools) => onChange({ mcpTools })}
            disabled={disabled}
          />
        </TabsPanel>
      )}
      {tab === "tool" && (
        <TabsPanel>
          <p className="mb-2 text-xs text-muted-foreground">内置工具绑定；创建智能体后生效。</p>
          <ToolsMatrix
            tools={tools}
            value={draft.toolSlugs}
            onChange={(toolSlugs) => onChange({ toolSlugs })}
            disabled={disabled}
          />
        </TabsPanel>
      )}
    </div>
  );
}
