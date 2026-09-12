import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import AgentForm from "@/components/agents/AgentForm";

vi.mock("@/api/agents", () => ({
  useModels: () => ({ data: [{ name: "qwen2.5:7b-instruct-q4_K_M", size_mb: 4700 }] }),
  useTools: () => ({ data: [] }),
}));

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
