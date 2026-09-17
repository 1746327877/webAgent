import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { MessageSquarePlus } from "lucide-react";
import { useAgents } from "@/api/agents";
import { useCreateSession } from "@/api/sessions";
import AgentAvatar from "@/components/agents/AgentAvatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { toast } from "@/stores/toast";

export default function AgentsPage() {
  const { data: agents, isLoading, error } = useAgents();
  const navigate = useNavigate();
  const createSession = useCreateSession();
  const [startingId, setStartingId] = useState<string | null>(null);

  /** 进入对话：为该智能体新建一个会话并跳转（卡片其他区域仍然是进编辑页） */
  async function startChat(agentId: string) {
    if (startingId) return;
    setStartingId(agentId);
    try {
      const session = await createSession.mutateAsync(agentId);
      navigate(`/sessions/${session.id}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "创建会话失败");
    } finally {
      setStartingId(null);
    }
  }

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
            // 外层用 relative 包一层：进入对话的按钮放在 Link 之外，
            // 既不破坏链接语义（整卡可编辑），也不会让按钮嵌在 <a> 里
            <div key={a.id} className="relative">
              <Link to={`/agents/${a.id}`} className="block">
                <Card className="h-full transition-colors hover:bg-accent/40">
                  <CardContent className="flex items-start gap-3 pr-12">
                    <AgentAvatar
                      agentId={a.id}
                      name={a.name}
                      hasAvatar={a.has_avatar}
                      version={a.updated_at}
                      className="size-9 text-lg"
                    />
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
              <Button
                type="button"
                variant="outline"
                size="icon"
                aria-label={`和「${a.name}」对话`}
                title="进入对话（新建会话）"
                disabled={startingId !== null}
                onClick={() => void startChat(a.id)}
                className="absolute right-2 top-2 z-10"
              >
                <MessageSquarePlus className="size-4" />
              </Button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
