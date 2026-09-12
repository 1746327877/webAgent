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

export default function Composer({ onSend, onStop, generating, agents = [] }: Props) {
  const [input, setInput] = useState("");
  const [mentionQuery, setMentionQuery] = useState<string | null>(null);
  const [mentionIds, setMentionIds] = useState<string[]>([]);
  const [activeIndex, setActiveIndex] = useState(0);

  const options =
    mentionQuery === null
      ? []
      : agents.filter((a) => a.name.includes(mentionQuery)).slice(0, 5);

  function onChange(value: string) {
    setInput(value);
    const match = value.match(MENTION_TAIL);
    setMentionQuery(match ? match[1] : null);
    setActiveIndex(0);
  }

  function select(agent: MentionAgent) {
    setInput((prev) => prev.replace(/@[^\s@]*$/, `@${agent.name}`));
    setMentionIds((prev) => (prev.includes(agent.id) ? prev : [...prev, agent.id]));
    setMentionQuery(null);
    setActiveIndex(0);
  }

  function submit() {
    const text = input.trim();
    if (!text || generating) return;
    // 选过但文本里已删掉的 @ 名字不再提交（例如用户退格删除了提及）
    const validIds = mentionIds.filter((id) => {
      const agent = agents.find((a) => a.id === id);
      return agent ? text.includes(agent.name) : false;
    });
    setInput("");
    setMentionIds([]);
    setMentionQuery(null);
    onSend(text, validIds);
  }

  return (
    <div className="flex gap-2 border-t p-3">
      <div className="relative flex-1">
        {mentionQuery !== null && options.length > 0 && (
          <Card
            size="sm"
            role="listbox"
            aria-label="提及智能体"
            className="absolute bottom-full left-0 z-10 mb-2 w-56 gap-0.5 p-1"
          >
            {options.map((a, i) => (
              <Button
                key={a.id}
                type="button"
                variant="ghost"
                size="sm"
                role="option"
                aria-selected={i === activeIndex}
                className={cn("w-full justify-start font-normal", i === activeIndex && "bg-muted")}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => select(a)}
              >
                <span>{a.emoji}</span>
                <span>{a.name}</span>
              </Button>
            ))}
          </Card>
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
