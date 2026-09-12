import { Link, useNavigate } from "react-router-dom";
import { useAgents } from "@/api/agents";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export default function AgentsPage() {
  const { data: agents, isLoading, error } = useAgents();
  const navigate = useNavigate();

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto max-w-4xl space-y-4 p-6">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-semibold">智能体</h1>
          <Button onClick={() => navigate("/agents/new")}>＋ 新建智能体</Button>
        </div>

        {isLoading && <p className="text-sm text-muted-foreground">加载中…</p>}
        {error && <p className="text-sm text-red-500">{error.message}</p>}
        {!isLoading && !error && agents?.length === 0 && (
          <p className="text-sm text-muted-foreground">还没有智能体，点击右上角「新建智能体」开始。</p>
        )}

        <div className="grid gap-3 sm:grid-cols-2">
          {agents?.map((a) => (
            <Link key={a.id} to={`/agents/${a.id}`} className="block">
              <Card className="h-full transition-colors hover:bg-accent/40">
                <CardContent className="flex items-start gap-3">
                  <span className="text-2xl leading-none">{a.emoji}</span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{a.name}</p>
                    <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">
                      {a.description || "暂无描述"}
                    </p>
                    <div className="mt-2 flex flex-wrap items-center gap-1.5">
                      {a.tags.map((t) => (
                        <Badge key={t} variant="outline">{t}</Badge>
                      ))}
                      <Badge variant={a.status === "published" ? "default" : "secondary"}>
                        {a.status === "published" ? "已发布" : "草稿"}
                      </Badge>
                      <span className="ml-auto text-xs text-muted-foreground">v{a.current_version}</span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
