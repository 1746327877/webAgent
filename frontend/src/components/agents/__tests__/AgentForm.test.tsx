import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import AgentForm from "@/components/agents/AgentForm";

vi.mock("@/components/ui/slider", () => ({ Slider: () => null }));

const models = vi.hoisted(() => ({
  list: [] as { name: string; size_mb: number | null; capabilities?: string[] }[],
}));

vi.mock("@/api/agents", () => ({
  useModels: () => ({ data: models.list }),
  useTools: () => ({ data: [] }),
  useUploadAgentAvatar: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteAgentAvatar: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

beforeEach(() => {
  models.list = [
    { name: "qwen2.5:7b-instruct-q4_K_M", size_mb: 4700, capabilities: ["completion", "tools"] },
  ];
});

test("提示词变量实时提取为 chips", async () => {
  render(<AgentForm initial={{ system_prompt: "你是{{agent.name}}，用户 {{user.name}}" }} onSubmit={vi.fn()} />);
  expect(screen.getByText("agent.name")).toBeInTheDocument();
  expect(screen.getByText("user.name")).toBeInTheDocument();
});

test("提交回传包含名称与温度", async () => {
  const onSubmit = vi.fn();
  render(<AgentForm initial={{ name: "A", model_config: { model: "m", temperature: 0.7 } }} onSubmit={onSubmit} />);
  await userEvent.clear(screen.getByLabelText("名称"));
  await userEvent.type(screen.getByLabelText("名称"), "B");
  await userEvent.click(screen.getByRole("button", { name: "保存" }));
  expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ name: "B" }));
});

test("模型支持 tools 时给出提示", () => {
  render(<AgentForm onSubmit={vi.fn()} />);
  expect(screen.getByText(/模型声明支持 tools/)).toBeInTheDocument();
});

test("模型不支持 tools 时警告且下拉标注", () => {
  models.list = [{ name: "bge-m3:latest", size_mb: 1200, capabilities: ["embedding"] }];
  render(<AgentForm onSubmit={vi.fn()} />);
  expect(screen.getByText(/未声明 tools 能力/)).toBeInTheDocument();
  expect(screen.getByRole("option", { name: /bge-m3:latest（不支持工具）/ })).toBeInTheDocument();
});

test("无法获取模型能力时提示未知", () => {
  models.list = [{ name: "mystery:1b", size_mb: null, capabilities: [] }];
  render(<AgentForm onSubmit={vi.fn()} />);
  expect(screen.getByText(/未能获取模型能力/)).toBeInTheDocument();
});
