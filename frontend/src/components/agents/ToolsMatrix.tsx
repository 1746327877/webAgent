import type { ToolInfo } from "@/api/agents";
import { Badge } from "@/components/ui/badge";

export interface ToolsMatrixProps {
  tools: ToolInfo[];
  value: string[];
  onChange: (slugs: string[]) => void;
  disabled?: boolean;
}

export default function ToolsMatrix({
  tools,
  value,
  onChange,
  disabled = false,
}: ToolsMatrixProps) {
  function toggle(slug: string, checked: boolean) {
    onChange(checked ? [...value.filter((s) => s !== slug), slug] : value.filter((s) => s !== slug));
  }

  if (tools.length === 0) {
    return <p className="text-sm text-muted-foreground">暂无可绑定的工具。</p>;
  }

  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {tools.map((tool) => (
        <div key={tool.slug} className="flex items-start gap-2 rounded-lg border border-border p-3">
          <input
            id={`tool-${tool.slug}`}
            type="checkbox"
            className="mt-0.5 size-4 shrink-0 accent-primary"
            checked={value.includes(tool.slug)}
            disabled={disabled}
            onChange={(e) => toggle(tool.slug, e.target.checked)}
          />
          <div className="min-w-0 flex-1">
            <label htmlFor={`tool-${tool.slug}`} className="cursor-pointer text-sm font-medium">
              {tool.name}
            </label>
            <p className="mt-0.5 text-xs text-muted-foreground">{tool.description}</p>
            <Badge variant="outline" className="mt-1.5">{tool.category}</Badge>
          </div>
        </div>
      ))}
    </div>
  );
}
