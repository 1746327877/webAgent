import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface Props {
  onSend: (text: string) => void;
  onStop: () => void;
  generating: boolean;
}

export default function Composer({ onSend, onStop, generating }: Props) {
  const [input, setInput] = useState("");

  function submit() {
    const text = input.trim();
    if (!text || generating) return;
    setInput("");
    onSend(text);
  }

  return (
    <div className="flex gap-2 border-t p-3">
      <Input
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        }}
        placeholder="输入问题，Enter 发送"
      />
      {generating ? (
        <Button variant="secondary" onClick={onStop}>停止</Button>
      ) : (
        <Button onClick={submit}>发送</Button>
      )}
    </div>
  );
}
