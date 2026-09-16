import { useState } from "react";
import {
  useCreateMcpServer,
  useProbeMcpConfig,
  useUpdateMcpServer,
  type McpConfigInput,
  type McpProbeResult,
  type McpServer,
  type McpTransport,
} from "@/api/mcp";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "@/stores/toast";

interface KV {
  key: string;
  value: string;
}

function toRows(obj: Record<string, string> | undefined): KV[] {
  return Object.entries(obj ?? {}).map(([key, value]) => ({ key, value }));
}

function fromRows(rows: KV[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const row of rows) {
    const key = row.key.trim();
    if (key) out[key] = row.value;
  }
  return out;
}

function KeyValueEditor({
  label,
  rows,
  onChange,
  keyPlaceholder,
  valuePlaceholder,
}: {
  label: string;
  rows: KV[];
  onChange: (rows: KV[]) => void;
  keyPlaceholder: string;
  valuePlaceholder: string;
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium">{label}</p>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => onChange([...rows, { key: "", value: "" }])}
        >
          ＋ 添加
        </Button>
      </div>
      {rows.length === 0 && <p className="text-xs text-muted-foreground">未设置</p>}
      {rows.map((row, index) => (
        <div key={index} className="flex items-center gap-2">
          <Input
            aria-label={`${label}名`}
            placeholder={keyPlaceholder}
            value={row.key}
            onChange={(e) =>
              onChange(rows.map((r, i) => (i === index ? { ...r, key: e.target.value } : r)))
            }
          />
          <Input
            aria-label={`${label}值`}
            placeholder={valuePlaceholder}
            value={row.value}
            onChange={(e) =>
              onChange(rows.map((r, i) => (i === index ? { ...r, value: e.target.value } : r)))
            }
          />
          <Button
            type="button"
            variant="ghost"
            size="sm"
            aria-label={`删除${label}`}
            onClick={() => onChange(rows.filter((_, i) => i !== index))}
          >
            ×
          </Button>
        </div>
      ))}
    </div>
  );
}

export default function McpForm({
  initial,
  onSaved,
  onCancel,
}: {
  initial?: McpServer | null;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const create = useCreateMcpServer();
  const update = useUpdateMcpServer();
  const probe = useProbeMcpConfig();

  const [name, setName] = useState(initial?.name ?? "");
  const [transport, setTransport] = useState<McpTransport>(initial?.transport ?? "http");
  const [url, setUrl] = useState(initial?.url ?? "");
  const [headers, setHeaders] = useState<KV[]>(toRows(initial?.headers));
  const [command, setCommand] = useState(initial?.command ?? "");
  const [argsText, setArgsText] = useState((initial?.args ?? []).join("\n"));
  const [env, setEnv] = useState<KV[]>(toRows(initial?.env));

  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<McpProbeResult | null>(null);

  const saving = create.isPending || update.isPending;

  function buildPayload(): McpConfigInput {
    const base: McpConfigInput = { name: name.trim(), transport };
    if (transport === "http") {
      return { ...base, url: url.trim(), headers: fromRows(headers) };
    }
    return {
      ...base,
      command: command.trim(),
      args: argsText
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean),
      env: fromRows(env),
    };
  }

  function validate(): string | null {
    if (!name.trim()) return "请填写名称";
    if (transport === "http") {
      const trimmed = url.trim();
      if (!trimmed) return "http 连接需要填写 url";
      if (!/^https?:\/\//i.test(trimmed)) return "url 需以 http:// 或 https:// 开头";
    } else if (!command.trim()) {
      return "stdio 连接需要填写 command";
    }
    return null;
  }

  async function onTest() {
    const invalid = validate();
    if (invalid) {
      setError(invalid);
      return;
    }
    setError(null);
    setResult(null);
    try {
      setResult(await probe.mutateAsync(buildPayload()));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "测试连接失败");
    }
  }

  async function onSave() {
    const invalid = validate();
    if (invalid) {
      setError(invalid);
      return;
    }
    setError(null);
    try {
      if (initial) {
        await update.mutateAsync({ id: initial.id, patch: buildPayload() });
      } else {
        await create.mutateAsync(buildPayload());
      }
      onSaved();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "保存失败");
    }
  }

  return (
    <Card>
      <CardContent className="space-y-4">
        <p className="font-medium">{initial ? `编辑 MCP：${initial.name}` : "新建 MCP"}</p>

        <div className="space-y-1.5">
          <label className="text-xs font-medium" htmlFor="mcp-name">
            名称
          </label>
          <Input
            id="mcp-name"
            placeholder="例如：百度搜索"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>

        <div className="space-y-1.5">
          <p className="text-xs font-medium">连接方式</p>
          <div className="flex gap-2" role="radiogroup" aria-label="连接方式">
            {(["http", "stdio"] as McpTransport[]).map((value) => (
              <Button
                key={value}
                type="button"
                role="radio"
                aria-checked={transport === value}
                variant={transport === value ? "default" : "outline"}
                size="sm"
                onClick={() => setTransport(value)}
              >
                {value}
              </Button>
            ))}
          </div>
        </div>

        {transport === "http" ? (
          <>
            <div className="space-y-1.5">
              <label className="text-xs font-medium" htmlFor="mcp-url">
                URL
              </label>
              <Input
                id="mcp-url"
                placeholder="https://example.com/mcp"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
            </div>
            <KeyValueEditor
              label="请求头"
              rows={headers}
              onChange={setHeaders}
              keyPlaceholder="Authorization"
              valuePlaceholder="Bearer sk-..."
            />
            <p className="text-xs text-muted-foreground">
              需要鉴权的 MCP 必须填（如 Authorization: Bearer &lt;Token&gt;，只放 ASCII）；公开服务可留空。
            </p>
          </>
        ) : (
          <>
            <div className="space-y-1.5">
              <label className="text-xs font-medium" htmlFor="mcp-command">
                命令
              </label>
              <Input
                id="mcp-command"
                placeholder="例如：npx"
                value={command}
                onChange={(e) => setCommand(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-medium" htmlFor="mcp-args">
                参数（每行一个）
              </label>
              <Textarea
                id="mcp-args"
                placeholder={"-y\n@modelcontextprotocol/server-filesystem\n."}
                value={argsText}
                onChange={(e) => setArgsText(e.target.value)}
              />
            </div>
            <KeyValueEditor
              label="环境变量"
              rows={env}
              onChange={setEnv}
              keyPlaceholder="KEY"
              valuePlaceholder="value"
            />
          </>
        )}

        {error && <p className="text-sm text-red-500">{error}</p>}
        {result && (
          <div className="space-y-1 rounded-lg border p-2">
            {result.ok ? (
              <p className="text-sm text-green-600">
                连接成功（{result.latency_ms ?? 0}ms）· 发现 {result.tools.length} 个工具
              </p>
            ) : (
              <p className="text-sm text-red-500">连接失败：{result.error}</p>
            )}
            {result.tools.length > 0 && (
              <ul className="space-y-0.5">
                {result.tools.map((tool) => (
                  <li key={tool.name} className="text-xs text-muted-foreground">
                    <code className="text-foreground">{tool.name}</code>
                    {tool.description ? ` · ${tool.description}` : ""}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        <div className="flex gap-2">
          <Button type="button" variant="outline" onClick={onTest} disabled={probe.isPending}>
            {probe.isPending ? "测试中…" : "测试连接"}
          </Button>
          <Button type="button" onClick={onSave} disabled={saving}>
            {saving ? "保存中…" : "保存"}
          </Button>
          <Button type="button" variant="ghost" onClick={onCancel}>
            取消
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
