import { render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

const mockState = vi.hoisted(() => ({
  artifacts: [] as unknown[],
  body: "",
  status: 200,
}));

vi.mock("@/api/artifacts", () => ({
  useArtifacts: () => ({ data: mockState.artifacts, isLoading: false }),
  artifactFileUrl: (id: string) => `/api/v1/artifacts/${id}`,
  downloadArtifact: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  apiFetch: async () => new Response(mockState.body, { status: mockState.status }),
  apiJson: async () => ({}),
  apiErrorMessage: () => "",
}));

import ArtifactPanel from "@/components/chat/ArtifactPanel";

const MARKDOWN_ARTIFACT = {
  id: "a1",
  session_id: "s1",
  source: "export",
  filename: "会议纪要测试.md",
  mime_type: "text/markdown",
  size_bytes: 2048,
  created_at: "2026-09-17T00:00:00Z",
};

beforeEach(() => {
  mockState.artifacts = [];
  mockState.body = "";
  mockState.status = 200;
});

test("没有产物时给出导出引导", () => {
  render(<ArtifactPanel sessionId="s1" onClose={vi.fn()} />);
  expect(screen.getByText(/还没有产物/)).toBeInTheDocument();
});

test("产物列表显示文件名与大小，并渲染 Markdown 预览", async () => {
  mockState.artifacts = [MARKDOWN_ARTIFACT];
  mockState.body = "# 会议纪要\n\n- 待办：发布";
  render(<ArtifactPanel sessionId="s1" onClose={vi.fn()} />);

  expect(screen.getByText(/会议纪要测试\.md/)).toBeInTheDocument();
  // 大小同时出现在列表项与预览头部，因此用 getAllByText
  expect(screen.getAllByText(/2\.0 KB/).length).toBeGreaterThan(0);
  // 预览走鉴权接口取文本后用 markdown 渲染
  expect(await screen.findByRole("heading", { name: "会议纪要" })).toBeInTheDocument();
  expect(screen.getByText(/待办：发布/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "下载" })).toBeInTheDocument();
});

test("取产物失败时提示错误而不是空白", async () => {
  mockState.artifacts = [MARKDOWN_ARTIFACT];
  mockState.status = 404;
  render(<ArtifactPanel sessionId="s1" onClose={vi.fn()} />);
  expect(await screen.findByText(/加载失败（HTTP 404）/)).toBeInTheDocument();
});
