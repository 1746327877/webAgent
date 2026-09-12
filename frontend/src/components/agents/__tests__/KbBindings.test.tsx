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
        id: "k0",
        name: "内部 wiki",
        description: null,
        embedding_model: "bge-m3",
        chunk_size: 512,
        chunk_overlap: 64,
        created_at: "2026-09-12T00:00:00Z",
      },
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

interface SavedBinding {
  kb_id: string;
  top_k: number;
  score_threshold: number;
}

test("勾选知识库后保存绑定并保留 score_threshold", async () => {
  render(
    <KbBindings
      agentId="a1"
      bindings={[{ kb_id: "k0", name: "内部 wiki", top_k: 8, score_threshold: 0.5 }]}
      editable
    />,
  );
  await userEvent.click(screen.getByLabelText("产品手册"));
  await userEvent.click(screen.getByRole("button", { name: "保存知识库绑定" }));

  expect(mutateAsync).toHaveBeenCalledTimes(1);
  const arg = mutateAsync.mock.calls[0][0] as { agentId: string; bindings: SavedBinding[] };
  expect(arg.agentId).toBe("a1");
  expect(arg.bindings).toHaveLength(2);
  const existing = arg.bindings.find((b) => b.kb_id === "k0");
  const added = arg.bindings.find((b) => b.kb_id === "k1");
  expect(existing).toMatchObject({ top_k: 8, score_threshold: 0.5 });
  expect(added).toMatchObject({ top_k: 5, score_threshold: 0.3 });
});
