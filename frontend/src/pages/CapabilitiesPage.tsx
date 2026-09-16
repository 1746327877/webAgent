import { useState } from "react";
import McpPanel from "@/components/capabilities/McpPanel";
import ParserPanel from "@/components/capabilities/ParserPanel";
import SkillList from "@/components/capabilities/SkillList";
import ToolList from "@/components/capabilities/ToolList";
import { Tabs, TabsPanel } from "@/components/ui/tabs";

const TABS = [
  { key: "skill", label: "Skill" },
  { key: "mcp", label: "MCP" },
  { key: "tool", label: "Tool" },
  { key: "parser", label: "解析" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

export default function CapabilitiesPage() {
  const [tab, setTab] = useState<TabKey>("skill");

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto max-w-4xl space-y-4 p-6">
        <div>
          <h1 className="text-xl font-semibold">🧩 扩展能力</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            系统当前拥有的 Skill、MCP 与 Tool。Skill / Tool 由代码内置，MCP 可手动接入。
          </p>
        </div>

        <Tabs
          value={tab}
          onChange={(key) => setTab(key as TabKey)}
          items={TABS}
          ariaLabel="扩展能力分类"
        />

        {tab === "skill" && (
          <TabsPanel>
            <SkillList />
          </TabsPanel>
        )}
        {tab === "mcp" && (
          <TabsPanel>
            <McpPanel />
          </TabsPanel>
        )}
        {tab === "tool" && (
          <TabsPanel>
            <ToolList />
          </TabsPanel>
        )}
        {tab === "parser" && (
          <TabsPanel>
            <ParserPanel />
          </TabsPanel>
        )}
      </div>
    </div>
  );
}
