import { useEffect, useMemo, useRef, useState } from "react";
import {
  useDeleteAgentAvatar,
  useModels,
  useUploadAgentAvatar,
  type AgentItem,
  type ModelInfo,
} from "@/api/agents";
import AgentAvatar from "@/components/agents/AgentAvatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "@/stores/toast";

const VARIABLE_RE = /\{\{\s*([\w.]+)\s*\}\}/g;

function extractVariables(text: string): string[] {
  return Array.from(new Set(Array.from(text.matchAll(VARIABLE_RE), (m) => m[1])));
}

export interface AgentFormProps {
  initial?: Partial<AgentItem>;
  onSubmit: (payload: Partial<AgentItem>) => void;
  saving?: boolean;
  /**
   * 新建态：把选中的头像文件交给外层（创建成功后再上传）；
   * 不传则在编辑态就地上传。
   */
  onAvatarChange?: (file: File | null) => void;
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

/** 提示所选模型是否具备工具调用能力（决定工具/MCP 绑定能否生效）。 */
function ModelToolHint({ model, models }: { model: string; models: ModelInfo[] }) {
  const info = models.find((m) => m.name === model);
  const caps = info?.capabilities ?? [];

  if (caps.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">
        未能获取模型能力（Ollama 不可用或该模型未安装，无法判断是否支持工具调用）。
      </p>
    );
  }
  if (!caps.includes("tools")) {
    return (
      <p className="text-xs text-red-500">
        该模型未声明 tools 能力：绑定的工具 / MCP 不会被调用，建议改用支持工具调用的模型（如
        qwen2.5）。
      </p>
    );
  }
  return (
    <p className="text-xs text-muted-foreground">
      模型声明支持 tools。注意：个别推理模型（如 deepseek-r1）声明了 tools
      但实际不产生工具调用，若工具不生效请改用 qwen2.5。
    </p>
  );
}

export default function AgentForm({
  initial,
  onSubmit,
  saving = false,
  onAvatarChange,
}: AgentFormProps) {
  const { data: models } = useModels();
  const uploadAvatar = useUploadAgentAvatar();
  const deleteAvatar = useDeleteAgentAvatar();
  const [name, setName] = useState(initial?.name ?? "");
  const [avatarFile, setAvatarFile] = useState<File | null>(null);
  const [avatarPreview, setAvatarPreview] = useState<string | null>(null);
  const avatarInputRef = useRef<HTMLInputElement>(null);
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

  // 卸载时释放本地预览 URL，避免泄漏
  useEffect(
    () => () => {
      setAvatarPreview((url) => {
        if (url) URL.revokeObjectURL(url);
        return null;
      });
    },
    [],
  );

  function onPickAvatar(file: File) {
    const url = URL.createObjectURL(file);
    setAvatarPreview((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return url;
    });
    setAvatarFile(file);
    if (onAvatarChange) {
      onAvatarChange(file);
      return;
    }
    // 编辑态：头像独立于表单，选完即上传
    if (initial?.id) {
      void uploadAvatar
        .mutateAsync({ id: initial.id, file })
        .then(() => toast.success("头像已更新"))
        .catch((err) => toast.error(err instanceof Error ? err.message : "头像上传失败"));
    }
  }

  function onRemoveAvatar() {
    setAvatarPreview((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
    setAvatarFile(null);
    if (onAvatarChange) {
      onAvatarChange(null);
      return;
    }
    if (initial?.id && initial.has_avatar) {
      void deleteAvatar
        .mutateAsync(initial.id)
        .then(() => toast.success("头像已移除"))
        .catch((err) => toast.error(err instanceof Error ? err.message : "移除头像失败"));
    }
  }

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
      description: description.trim(),
      tags: splitComma(tagsText).slice(0, 5),
      system_prompt: systemPrompt,
      model_config: {
        ...config,
        model: selectedModel,
        temperature: Number.isFinite(temperature) ? temperature : 0.7,
        top_p: Number.isFinite(topP) ? topP : 0.9,
        max_tokens: clampInt(maxTokens, 128, 8192, 2048),
        num_ctx: clampInt(numCtx, 2048, 262144, 8192),
      },
      welcome_msg: welcomeMsg.trim(),
      examples: splitLines(examplesText).slice(0, 5),
    });
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <div className="flex items-center gap-3">
        <AgentAvatar
          agentId={initial?.id}
          name={name || "新智能体"}
          hasAvatar={Boolean(initial?.has_avatar)}
          version={initial?.updated_at}
          previewUrl={avatarPreview ?? undefined}
          className="size-12 text-lg"
        />
        <div className="space-y-1">
          <div className="flex gap-2">
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => avatarInputRef.current?.click()}
              disabled={uploadAvatar.isPending || deleteAvatar.isPending}
            >
              上传头像
            </Button>
            {(avatarFile || avatarPreview || initial?.has_avatar) && (
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={onRemoveAvatar}
                disabled={uploadAvatar.isPending || deleteAvatar.isPending}
              >
                移除
              </Button>
            )}
          </div>
          <p className="text-xs text-muted-foreground">
            不上传时用「名字第一个字」作为头像（png/jpg/webp，≤ 2MB）
          </p>
        </div>
        <input
          ref={avatarInputRef}
          type="file"
          aria-label="上传头像"
          accept=".png,.jpg,.jpeg,.webp"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = ""; // 允许连续选择同一文件
            if (file) onPickAvatar(file);
          }}
        />
      </div>

      <div className="grid gap-4 sm:grid-cols-[1fr]">
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
            <option key={m.name} value={m.name}>
              {m.name}
              {(m.capabilities?.length ?? 0) > 0 && !m.capabilities?.includes("tools")
                ? "（不支持工具）"
                : ""}
            </option>
          ))}
        </select>
        <ModelToolHint model={selectedModel} models={models ?? []} />
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
            max={262144}
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
