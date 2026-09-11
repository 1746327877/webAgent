import { useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";
import { parseSSE } from "@/lib/sse";
import { useChatStore } from "@/stores/chat";

const MODEL = "qwen2.5:7b-instruct-q4_K_M";

export default function ChatPage() {
  const [input, setInput] = useState("");
  const { messages, generating, addMessage, appendToken, appendThinking, setGenerating } =
    useChatStore();

  async function send() {
    const text = input.trim();
    if (!text || generating) return;
    setInput("");
    addMessage({ role: "user", content: text, thinking: "" });
    addMessage({ role: "assistant", content: "", thinking: "" });
    setGenerating(true);
    try {
      const history = useChatStore
        .getState()
        .messages.filter((m) => m.role === "user" || m.content)
        .map((m) => ({ role: m.role, content: m.content }));
      const res = await apiFetch("/api/v1/chat/stream", {
        method: "POST",
        body: JSON.stringify({ model: MODEL, messages: history }),
      });
      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
      for await (const evt of parseSSE(res.body)) {
        if (evt.event === "token") appendToken((evt.data as { delta: string }).delta);
        if (evt.event === "thinking") appendThinking((evt.data as { delta: string }).delta);
        if (evt.event === "error") appendToken(`\n\n**错误**：${(evt.data as { message: string }).message}`);
      }
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div className="mx-auto flex h-screen max-w-3xl flex-col p-4">
      <h1 className="border-b pb-3 text-lg font-semibold">AI 专家工作台</h1>
      <div className="flex-1 space-y-4 overflow-y-auto py-4">
        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "text-right" : ""}>
            {m.thinking && (
              <details className="mb-1 text-sm text-muted-foreground">
                <summary>思考过程</summary>
                <p className="whitespace-pre-wrap">{m.thinking}</p>
              </details>
            )}
            {m.role === "user" ? (
              <span className="inline-block rounded-lg bg-primary px-3 py-2 text-primary-foreground">
                {m.content}
              </span>
            ) : (
              <div className="prose prose-sm max-w-none dark:prose-invert">
                <Markdown remarkPlugins={[remarkGfm]}>{m.content}</Markdown>
              </div>
            )}
          </div>
        ))}
      </div>
      <div className="flex gap-2 border-t pt-3">
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && send()}
          placeholder="输入问题，Enter 发送"
        />
        <Button onClick={send} disabled={generating}>
          {generating ? "生成中…" : "发送"}
        </Button>
      </div>
    </div>
  );
}
