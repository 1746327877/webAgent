import { useTools, type ToolInfo } from "@/api/agents";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

function ParamList({ schema }: { schema: ToolInfo["input_schema"] }) {
  const properties = schema?.properties ?? {};
  const required = new Set(schema?.required ?? []);
  const entries = Object.entries(properties);
  if (entries.length === 0) {
    return <p className="text-sm text-muted-foreground">无参数</p>;
  }
  return (
    <ul className="space-y-1">
      {entries.map(([name, spec]) => (
        <li key={name} className="text-sm text-muted-foreground">
          <code className="text-foreground">{name}</code>
          <span className="ml-2 text-xs">{spec.type ?? "string"}</span>
          <Badge variant="outline" className="ml-2">
            {required.has(name) ? "必填" : "可选"}
          </Badge>
          {spec.default !== undefined && (
            <span className="ml-2 text-xs">默认 {String(spec.default)}</span>
          )}
        </li>
      ))}
    </ul>
  );
}

export default function ToolList() {
  const { data, isLoading, error } = useTools();

  if (isLoading) return <p className="text-sm text-muted-foreground">加载中…</p>;
  if (error) return <p className="text-sm text-red-500">{error.message}</p>;
  if (!data?.length) return <p className="text-sm text-muted-foreground">暂无可用工具。</p>;

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        工具由代码内置，智能体在「工具绑定」里勾选后即可在对话中调用（function calling）。
      </p>
      {data.map((tool) => (
        <Card key={tool.slug}>
          <CardContent className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{tool.name}</span>
              <code className="text-xs text-muted-foreground">{tool.slug}</code>
              <Badge variant="outline">{tool.category}</Badge>
              {tool.is_system && <Badge variant="secondary">系统内置</Badge>}
            </div>
            <p className="text-sm text-muted-foreground">{tool.description}</p>
            <div>
              <p className="text-xs font-medium">参数</p>
              <ParamList schema={tool.input_schema} />
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
