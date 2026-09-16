import { useState } from "react";
import SessionListTab from "@/components/admin/SessionListTab";
import { Tabs, TabsPanel } from "@/components/ui/tabs";
import AdminDashboardPage from "@/pages/AdminDashboardPage";

const TABS = [
  { key: "overview", label: "概览" },
  { key: "sessions", label: "会话记录" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

export default function AdminPage() {
  const [tab, setTab] = useState<TabKey>("overview");

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto max-w-6xl space-y-4 p-6">
        <h1 className="text-xl font-semibold">📊 可观测性</h1>

        <Tabs
          value={tab}
          onChange={(key) => setTab(key as TabKey)}
          items={TABS}
          ariaLabel="可观测性分区"
        />

        {tab === "overview" && (
          <TabsPanel>
            <AdminDashboardPage />
          </TabsPanel>
        )}
        {tab === "sessions" && (
          <TabsPanel>
            <SessionListTab />
          </TabsPanel>
        )}
      </div>
    </div>
  );
}
