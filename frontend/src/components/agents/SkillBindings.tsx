import { useState } from "react";
import { useSetAgentSkills, type AgentItem } from "@/api/agents";
import { useSkills } from "@/api/capabilities";
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
  const { data: skills = [], isLoading } = useSkills();
  const setSkills = useSetAgentSkills();
  const initial = agent.skill_slugs ?? [];
  const [draft, setDraft] = useState<string[]>(initial);
  const dirty = [...draft].sort().join(",") !== [...initial].sort().join(",");

  function toggle(slug: string, checked: boolean) {
    setDraft(checked ? [...draft.filter((s) => s !== slug), slug] : draft.filter((s) => s !== slug));
  }

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

      {isLoading && <p className="text-sm text-muted-foreground">加载中…</p>}
      {!isLoading && skills.length === 0 && (
        <p className="text-sm text-muted-foreground">暂无可绑定的 Skill。</p>
      )}

      {skills.length > 0 && (
        <label className="flex cursor-pointer items-center gap-2 text-xs text-muted-foreground">
          <input
            type="checkbox"
            aria-label="全选 Skill"
            className="size-4 shrink-0 accent-primary"
            checked={skills.every((s) => draft.includes(s.slug))}
            ref={(el) => {
              const all = skills.every((s) => draft.includes(s.slug));
              const some = skills.some((s) => draft.includes(s.slug));
              if (el) el.indeterminate = some && !all;
            }}
            disabled={setSkills.isPending}
            onChange={(e) => setDraft(e.target.checked ? skills.map((s) => s.slug) : [])}
          />
          全选 / 清空（共 {skills.length} 个，已选 {draft.length} 个）
        </label>
      )}

      <div className="space-y-2">
        {skills.map((skill) => (
          <label
            key={skill.slug}
            className="flex cursor-pointer items-start gap-2 rounded-lg border p-3"
          >
            <input
              type="checkbox"
              className="mt-0.5 size-4 shrink-0 accent-primary"
              checked={draft.includes(skill.slug)}
              disabled={setSkills.isPending}
              onChange={(e) => toggle(skill.slug, e.target.checked)}
            />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium">
                {skill.icon} {skill.name}
                <code className="ml-2 text-xs text-muted-foreground">{skill.slug}</code>
              </p>
              <p className="mt-0.5 text-xs text-muted-foreground">{skill.summary}</p>
            </div>
          </label>
        ))}
      </div>
    </section>
  );
}
