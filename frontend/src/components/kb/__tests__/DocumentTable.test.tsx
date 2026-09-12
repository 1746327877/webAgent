import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import DocumentTable from "@/components/kb/DocumentTable";

const DOCS = [
  { id: "d1", kb_id: "k1", filename: "a.md", file_type: "md", size_bytes: 1, status: "ready", error: null, chunk_count: 3, created_at: "2026-09-12T00:00:00Z" },
  { id: "d2", kb_id: "k1", filename: "b.pdf", file_type: "pdf", size_bytes: 2, status: "failed", error: "扫描件", chunk_count: 0, created_at: "2026-09-12T00:00:00Z" },
];

test("状态徽章与失败重试", async () => {
  const onRetry = vi.fn();
  render(<DocumentTable documents={DOCS} onRetry={onRetry} onDelete={vi.fn()} />);
  expect(screen.getByText("就绪")).toBeInTheDocument();
  expect(screen.getByText("失败")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "重试" }));
  expect(onRetry).toHaveBeenCalledWith("d2");
});

test("处理中状态显示", () => {
  render(
    <DocumentTable
      documents={[{ ...DOCS[0], id: "d3", status: "embedding" }]}
      onRetry={vi.fn()}
      onDelete={vi.fn()}
    />,
  );
  expect(screen.getByText("处理中")).toBeInTheDocument();
});

test("删除按钮回调", async () => {
  const onDelete = vi.fn();
  render(<DocumentTable documents={[DOCS[0]]} onRetry={vi.fn()} onDelete={onDelete} />);
  await userEvent.click(screen.getByRole("button", { name: "删除" }));
  expect(onDelete).toHaveBeenCalledWith("d1");
});
