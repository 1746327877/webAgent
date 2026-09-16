import { useSkills } from "@/api/capabilities";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

export default function SkillList() {
  const { data, isLoading, error } = useSkills();

  if (isLoading) return <p className="text-sm text-muted-foreground">加载中…</p>;
  if (error) return <p className="text-sm text-red-500">{error.message}</p>;
  if (!data?.length) return <p className="text-sm text-muted-foreground">暂无内置 Skill。</p>;

  return (
    <div className="space-y-3">
      {data.map((skill) => (
        <Card key={skill.slug}>
          <CardContent className="space-y-2">
            <div className="flex items-center gap-2">
              <span className="text-xl leading-none">{skill.icon}</span>
              <span className="font-medium">{skill.name}</span>
              <code className="text-xs text-muted-foreground">{skill.slug}</code>
            </div>
            <p className="text-sm text-muted-foreground">{skill.summary}</p>
            <div>
              <p className="text-xs font-medium">使用方式</p>
              <p className="text-sm text-muted-foreground">{skill.usage}</p>
            </div>
            <div>
              <p className="text-xs font-medium">注入说明（绑定后进入 system prompt）</p>
              <p className="text-sm text-muted-foreground">{skill.instructions}</p>
            </div>
            {skill.examples.length > 0 && (
              <div className="flex flex-wrap gap-1.5 pt-0.5">
                {skill.examples.map((example) => (
                  <Badge key={example} variant="secondary">
                    {example}
                  </Badge>
                ))}
              </div>
            )}
            {skill.recommended_tools.length > 0 && (
              <p className="text-xs text-muted-foreground">
                推荐工具：{skill.recommended_tools.join("、")}
              </p>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
