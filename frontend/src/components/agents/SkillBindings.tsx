import { useState } from "react";
import { useSetAgentSkills, type AgentItem } from "@/api/agents";
import SkillSelector from "@/components/agents/SkillSelector";
import { Button } from "@/components/ui/button";

export default function SkillBindings({
  agent,
  onNotice,
  onError,
}: {
  agent: AgentItem;
  onNotice: (message: string) => void;
  onError: (message: string) => void;
}) {
  const initial = agent.skill_slugs ?? [];
  const [draft, setDraft] = useState<string[]>(initial);
  const setSkills = useSetAgentSkills();
  const dirty = [...draft].sort().join(",") !== [...initial].sort().join(",");

  async function onSave() {
    try {
      const res = await setSkills.mutateAsync({ id: agent.id, slugs: draft });
      setDraft(res.slugs ?? []);
      onNotice("Skill 绑定已保存");
    } catch (err) {
      onError(err instanceof Error ? err.message : "保存 Skill 绑定失败");
    }
  }

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-medium">Skill 绑定</h2>
          <p className="text-xs text-muted-foreground">
            绑定的 Skill 会把指令注入该智能体的 system prompt，从而改变回答行为。
          </p>
        </div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={setSkills.isPending || !dirty}
          onClick={onSave}
        >
          {setSkills.isPending ? "保存中…" : "保存 Skill 绑定"}
        </Button>
      </div>
      <SkillSelector value={draft} onChange={setDraft} disabled={setSkills.isPending} />
    </section>
  );
}
