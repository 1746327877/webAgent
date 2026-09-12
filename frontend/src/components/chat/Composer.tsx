import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "cn";

interface MentionAgent {
  id: string;
  name: string;
  emoji: string;
}

interface Props {
  onSend: (text: string, mentionIds: string[]) => void;
  onStop: () => void;
  generating: boolean;
  agents?: MentionAgent[];
}

const MENTION_TAIL = /@([^\s@]*)$/;
/** 后端 MessageIn.mentions 限制 max_length=2，前端同样封顶，避免必然 422 */
const MAX_MENTIONS = 2;

export default function Composer({ onSend, onStop, generating, agents = [] }: Props) {
  const [input, setInput] = useState("");
  const [mentionQuery, setMentionQuery] = useState<string | null>(null);
  const [mentionIds, setMentionIds] = useState<string[]>([]);
  const [activeIndex, setActiveIndex] = useState(0);

  const options =
    mentionQuery === null
      ? []
      : agents.filter((a) => a.name.includes(mentionQuery)).slice(0, 5);
  const atCap = mentionIds.length >= MAX_MENTIONS;

  function onChange(value: string) {
    setInput(value);
    const match = value.match(MENTION_TAIL);
    setMentionQuery(match ? match[1] : null);
    setActiveIndex(0);
  }

  function select(agent: MentionAgent) {
    // 已满 2 个时拒绝第三个；已选过的仍可补全文本但不重复记 id
    if (atCap && !mentionIds.includes(agent.id)) return;
    setInput((prev) => prev.replace(/@[^\s@]*$/, `@${agent.name}`));
    setMentionIds((prev) => (prev.includes(agent.id) ? prev : [...prev, agent.id]));
    setMentionQuery(null);
    setActiveIndex(0);
  }

  function submit() {
    const text = input.trim();
    if (!text || generating) return;
    // 选过但文本里已删掉的 @ 名字不再提交（例如用户退格删除了提及）
    const validIds = mentionIds
      .filter((id) => {
        const agent = agents.find((a) => a.id === id);
        return agent ? text.includes(agent.name) : false;
      })
      .slice(0, MAX_MENTIONS);
    setInput("");
    setMentionIds([]);
    setMentionQuery(null);
    onSend(text, validIds);
  }

  return (
    <div className="flex gap-2 border-t p-3">
      <div className="relative flex-1">
        {mentionQuery !== null && options.length > 0 && (
          <div className="absolute bottom-full left-0 z-10 mb-2 w-56">
            {atCap && (
              <p className="mb-1 rounded-md bg-muted px-2 py-1 text-xs text-muted-foreground">
                最多同时 @ 2 个智能体
              </p>
            )}
            <Card size="sm" role="listbox" aria-label="提及智能体" className="gap-0.5 p-1">
              {options.map((a, i) => (
                <Button
                  key={a.id}
                  type="button"
                  variant="ghost"
                  size="sm"
                  role="option"
                  aria-selected={i === activeIndex}
                  className={cn(
                    "w-full justify-start font-normal",
                    i === activeIndex && "bg-muted",
                  )}
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => select(a)}
                >
                  <span>{a.emoji}</span>
                  <span>{a.name}</span>
                </Button>
              ))}
            </Card>
          </div>
        )}
        <Input
          value={input}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (mentionQuery !== null && options.length > 0) {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setActiveIndex((i) => (i + 1) % options.length);
                return;
              }
              if (e.key === "ArrowUp") {
                e.preventDefault();
                setActiveIndex((i) => (i - 1 + options.length) % options.length);
                return;
              }
              if (e.key === "Enter") {
                e.preventDefault();
                select(options[Math.min(activeIndex, options.length - 1)]);
                return;
              }
            }
            if (e.key === "Escape") {
              setMentionQuery(null);
              return;
            }
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder="输入问题，Enter 发送"
        />
      </div>
      {generating ? (
        <Button variant="secondary" onClick={onStop}>停止</Button>
      ) : (
        <Button onClick={submit}>发送</Button>
      )}
    </div>
  );
}
