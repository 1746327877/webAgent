import { useMemo, useState } from "react";
import { useModels, type AgentItem } from "@/api/agents";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import { Textarea } from "@/components/ui/textarea";

const VARIABLE_RE = /\{\{\s*([\w.]+)\s*\}\}/g;

function extractVariables(text: string): string[] {
  return Array.from(new Set(Array.from(text.matchAll(VARIABLE_RE), (m) => m[1])));
}

export interface AgentFormProps {
  initial?: Partial<AgentItem>;
  onSubmit: (payload: Partial<AgentItem>) => void;
  saving?: boolean;
}

function toNumber(value: unknown): number {
  if (value === "" || value === null || value === undefined) return Number.NaN;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : Number.NaN;
}

function clampInt(value: number, min: number, max: number, fallback: number): number {
  if (!Number.isFinite(value)) return fallback;
  return Math.min(max, Math.max(min, Math.round(value)));
}

function splitComma(text: string): string[] {
  return text
    .split(/[,，]/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function splitLines(text: string): string[] {
  return text
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);
}

export default function AgentForm({ initial, onSubmit, saving = false }: AgentFormProps) {
  const { data: models } = useModels();
  const [name, setName] = useState(initial?.name ?? "");
  const [emoji, setEmoji] = useState(initial?.emoji ?? "🤖");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [tagsText, setTagsText] = useState((initial?.tags ?? []).join("，"));
  const [systemPrompt, setSystemPrompt] = useState(initial?.system_prompt ?? "");
  const [welcomeMsg, setWelcomeMsg] = useState(initial?.welcome_msg ?? "");
  const [examplesText, setExamplesText] = useState((initial?.examples ?? []).join("\n"));
  // 保留 model_config 里表单未覆盖的字段（provider/history_rounds 等），PATCH 时不丢配置
  const [config, setConfig] = useState<Record<string, unknown>>(() => ({
    temperature: 0.7,
    top_p: 0.9,
    max_tokens: 2048,
    num_ctx: 8192,
    ...(initial?.model_config ?? {}),
  }));

  const variables = useMemo(() => extractVariables(systemPrompt), [systemPrompt]);
  const model = typeof config.model === "string" ? config.model : "";
  const firstModel = models?.[0]?.name ?? "";
  // 未选择时默认使用第一个可用模型（不写入 state，提交时回传）
  const selectedModel = model || firstModel;
  const temperature = toNumber(config.temperature);
  const topP = toNumber(config.top_p);
  const maxTokens = toNumber(config.max_tokens);
  const numCtx = toNumber(config.num_ctx);

  function patchConfig(key: string, value: unknown) {
    setConfig((c) => ({ ...c, [key]: value }));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmedName = name.trim();
    if (!trimmedName || saving) return;
    onSubmit({
      name: trimmedName,
      emoji: emoji.trim() || "🤖",
      description: description.trim(),
      tags: splitComma(tagsText).slice(0, 5),
      system_prompt: systemPrompt,
      model_config: {
        ...config,
        model: selectedModel,
        temperature: Number.isFinite(temperature) ? temperature : 0.7,
        top_p: Number.isFinite(topP) ? topP : 0.9,
        max_tokens: clampInt(maxTokens, 128, 8192, 2048),
        num_ctx: clampInt(numCtx, 2048, 32768, 8192),
      },
      welcome_msg: welcomeMsg.trim(),
      examples: splitLines(examplesText).slice(0, 5),
    });
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-[7rem_1fr]">
        <div className="space-y-1">
          <label htmlFor="agent-emoji" className="text-sm">Emoji</label>
          <Input id="agent-emoji" value={emoji} maxLength={8}
                 onChange={(e) => setEmoji(e.target.value)} />
        </div>
        <div className="space-y-1">
          <label htmlFor="agent-name" className="text-sm">名称</label>
          <Input id="agent-name" value={name} maxLength={64} placeholder="例如：代码专家"
                 onChange={(e) => setName(e.target.value)} />
        </div>
      </div>

      <div className="space-y-1">
        <label htmlFor="agent-description" className="text-sm">描述</label>
        <Textarea id="agent-description" rows={2} value={description} placeholder="一句话说明这个智能体做什么"
                  onChange={(e) => setDescription(e.target.value)} />
      </div>

      <div className="space-y-1">
        <label htmlFor="agent-tags" className="text-sm">标签</label>
        <Input id="agent-tags" value={tagsText} placeholder="用逗号分隔，例如：开发，工具"
               onChange={(e) => setTagsText(e.target.value)} />
      </div>

      <div className="space-y-1">
        <label htmlFor="agent-system-prompt" className="text-sm">系统提示词</label>
        <Textarea id="agent-system-prompt" rows={6} value={systemPrompt}
                  placeholder="例如：你是{{agent.name}}，请用中文回答"
                  onChange={(e) => setSystemPrompt(e.target.value)} />
        {variables.length > 0 && (
          <div className="flex flex-wrap items-center gap-1 pt-1">
            <span className="text-xs text-muted-foreground">变量：</span>
            {variables.map((v) => (
              <Badge key={v} variant="secondary" className="font-mono">{v}</Badge>
            ))}
          </div>
        )}
      </div>

      <div className="space-y-1">
        <label htmlFor="agent-model" className="text-sm">模型</label>
        <select
          id="agent-model"
          className="h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-input/30"
          value={selectedModel}
          onChange={(e) => patchConfig("model", e.target.value)}
        >
          {selectedModel === "" && <option value="">请选择模型</option>}
          {selectedModel !== "" && !(models ?? []).some((m) => m.name === selectedModel) && (
            <option value={selectedModel}>{selectedModel}</option>
          )}
          {(models ?? []).map((m) => (
            <option key={m.name} value={m.name}>{m.name}</option>
          ))}
        </select>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm">温度</span>
            <span className="text-xs text-muted-foreground">
              {Number.isFinite(temperature) ? temperature.toFixed(2) : "-"}
            </span>
          </div>
          <Slider
            value={Number.isFinite(temperature) ? temperature : 0.7}
            min={0}
            max={2}
            step={0.05}
            onValueChange={(v) => patchConfig("temperature", Array.isArray(v) ? v[0] : v)}
          />
        </div>
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm">top_p</span>
            <span className="text-xs text-muted-foreground">
              {Number.isFinite(topP) ? topP.toFixed(2) : "-"}
            </span>
          </div>
          <Slider
            value={Number.isFinite(topP) ? topP : 0.9}
            min={0}
            max={1}
            step={0.05}
            onValueChange={(v) => patchConfig("top_p", Array.isArray(v) ? v[0] : v)}
          />
        </div>
        <div className="space-y-1">
          <label htmlFor="agent-max-tokens" className="text-sm">max_tokens</label>
          <Input
            id="agent-max-tokens"
            type="number"
            min={128}
            max={8192}
            value={Number.isFinite(maxTokens) ? maxTokens : ""}
            onChange={(e) => patchConfig("max_tokens", e.target.value === "" ? "" : e.target.valueAsNumber)}
          />
        </div>
        <div className="space-y-1">
          <label htmlFor="agent-num-ctx" className="text-sm">num_ctx</label>
          <Input
            id="agent-num-ctx"
            type="number"
            min={2048}
            max={32768}
            value={Number.isFinite(numCtx) ? numCtx : ""}
            onChange={(e) => patchConfig("num_ctx", e.target.value === "" ? "" : e.target.valueAsNumber)}
          />
        </div>
      </div>

      <div className="space-y-1">
        <label htmlFor="agent-welcome" className="text-sm">欢迎语</label>
        <Input id="agent-welcome" value={welcomeMsg} placeholder="空会话时展示给用户的话"
               onChange={(e) => setWelcomeMsg(e.target.value)} />
      </div>

      <div className="space-y-1">
        <label htmlFor="agent-examples" className="text-sm">示例问题</label>
        <Textarea id="agent-examples" rows={3} value={examplesText} placeholder="每行一条，例如：现在几点？"
                  onChange={(e) => setExamplesText(e.target.value)} />
      </div>

      <div className="pt-1">
        <Button type="submit" disabled={saving || !name.trim()}>
          {saving ? "保存中…" : "保存"}
        </Button>
      </div>
    </form>
  );
}
