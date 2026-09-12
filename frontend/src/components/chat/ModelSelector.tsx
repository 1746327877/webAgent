import { CheckIcon, ChevronDownIcon } from "lucide-react";
import { cn } from "cn";
import { buttonVariants } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

export interface ModelOption {
  name: string;
  size_mb: number | null;
}

interface Props {
  models: ModelOption[];
  /** 当前显式选择的模型；null 表示智能体默认 */
  value: string | null;
  /** 未选择时展示的智能体默认模型名 */
  defaultLabel: string;
  onChange: (model: string | null) => void;
}

/** 输入框内的模型下拉：选择仅覆盖随后发送消息的主回合模型 */
export default function ModelSelector({ models, value, defaultLabel, onChange }: Props) {
  const active = value ?? defaultLabel;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className={cn(buttonVariants({ variant: "outline", size: "sm" }), "max-w-56")}
        aria-label="选择模型"
      >
        <span className="truncate">{active}</span>
        <ChevronDownIcon />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-64">
        <DropdownMenuItem
          className={cn(value === null && "bg-muted")}
          onClick={() => onChange(null)}
        >
          {value === null && <CheckIcon className="size-3.5" />}
          <span className="truncate">使用智能体默认（{defaultLabel}）</span>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        {models.map((model) => (
          <DropdownMenuItem
            key={model.name}
            aria-current={value === model.name}
            className={cn(value === model.name && "bg-muted")}
            onClick={() => onChange(model.name)}
          >
            {value === model.name && <CheckIcon className="size-3.5" />}
            <span className="truncate">{model.name}</span>
            {model.size_mb != null && (
              <span className="ml-auto text-xs text-muted-foreground">
                {Math.round(model.size_mb)}MB
              </span>
            )}
          </DropdownMenuItem>
        ))}
        {models.length === 0 && (
          <DropdownMenuItem disabled>暂无可用模型</DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
