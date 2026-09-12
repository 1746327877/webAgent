import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

const mutateAsync = vi.hoisted(() => vi.fn().mockResolvedValue({ bindings: [] }));

vi.mock("@/api/agents", () => ({
  useSetAgentKbs: () => ({ mutateAsync, isPending: false }),
}));

vi.mock("@/api/kbs", () => ({
  useKbs: () => ({
    data: [
      {
        id: "k1",
        name: "产品手册",
        description: null,
        embedding_model: "bge-m3",
        chunk_size: 512,
        chunk_overlap: 64,
        created_at: "2026-09-12T00:00:00Z",
      },
    ],
  }),
}));

import KbBindings from "@/components/agents/KbBindings";

test("勾选知识库后保存绑定并携带 kb_id", async () => {
  render(<KbBindings agentId="a1" bindings={[]} editable />);
  await userEvent.click(screen.getByLabelText("产品手册"));
  await userEvent.click(screen.getByRole("button", { name: "保存知识库绑定" }));

  expect(mutateAsync).toHaveBeenCalledTimes(1);
  const arg = mutateAsync.mock.calls[0][0] as {
    agentId: string;
    bindings: { kb_id: string; top_k: number }[];
  };
  expect(arg.agentId).toBe("a1");
  expect(arg.bindings).toHaveLength(1);
  expect(arg.bindings[0].kb_id).toBe("k1");
  expect(arg.bindings[0].top_k).toBe(5);
});
