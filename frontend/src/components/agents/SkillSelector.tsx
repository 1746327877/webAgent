import { useSkills } from "@/api/capabilities";

export interface SkillSelectorProps {
  value: string[];
  onChange: (slugs: string[]) => void;
  disabled?: boolean;
}

/** 受控 Skill 选择器（带全选/清空）；保存逻辑由外层负责，便于"新建"时先攒后存。 */
export default function SkillSelector({ value, onChange, disabled = false }: SkillSelectorProps) {
  const { data: skills = [], isLoading } = useSkills();

  if (isLoading) return <p className="text-sm text-muted-foreground">加载中…</p>;
  if (skills.length === 0) {
    return <p className="text-sm text-muted-foreground">暂无可绑定的 Skill。</p>;
  }

  const allChecked = skills.every((s) => value.includes(s.slug));
  const someChecked = skills.some((s) => value.includes(s.slug));

  return (
    <div className="space-y-2">
      <label className="flex cursor-pointer items-center gap-2 text-xs text-muted-foreground">
        <input
          type="checkbox"
          aria-label="全选 Skill"
          className="size-4 shrink-0 accent-primary"
          checked={allChecked}
          ref={(el) => {
            if (el) el.indeterminate = someChecked && !allChecked;
          }}
          disabled={disabled}
          onChange={(e) => onChange(e.target.checked ? skills.map((s) => s.slug) : [])}
        />
        全选 / 清空（共 {skills.length} 个，已选 {value.length} 个）
      </label>

      {skills.map((skill) => (
        <label
          key={skill.slug}
          className="flex cursor-pointer items-start gap-2 rounded-lg border p-3"
        >
          <input
            type="checkbox"
            className="mt-0.5 size-4 shrink-0 accent-primary"
            checked={value.includes(skill.slug)}
            disabled={disabled}
            onChange={(e) =>
              onChange(
                e.target.checked
                  ? [...value.filter((s) => s !== skill.slug), skill.slug]
                  : value.filter((s) => s !== skill.slug),
              )
            }
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
  );
}
