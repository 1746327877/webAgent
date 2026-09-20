import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

const mockState = vi.hoisted(() => ({
  artifacts: [] as unknown[],
  body: "",
  status: 200,
  fetchedUrls: [] as string[],
}));

vi.mock("@/api/artifacts", () => ({
  useArtifacts: () => ({ data: mockState.artifacts, isLoading: false }),
  artifactFileUrl: (id: string) => `/api/v1/artifacts/${id}`,
  artifactPreviewUrl: (id: string) => `/api/v1/artifacts/${id}/preview`,
  downloadArtifact: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  apiFetch: async (url: string) => {
    mockState.fetchedUrls.push(url);
    return new Response(mockState.body, { status: mockState.status });
  },
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
  mockState.fetchedUrls = [];
  localStorage.clear();
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

test("纪要类产物里 `## 我` / `## 助手` 显示身份徽章框", async () => {
  mockState.artifacts = [MARKDOWN_ARTIFACT];
  mockState.body = "## 我\n\n你好\n\n## 助手\n\n好的";
  render(<ArtifactPanel sessionId="s1" onClose={vi.fn()} />);
  expect(await screen.findByRole("heading", { name: "我" })).toHaveClass(
    "border-sky-500/40",
  );
  expect(screen.getByRole("heading", { name: "助手" })).toHaveClass(
    "border-emerald-500/40",
  );
});

const DOCX_ARTIFACT = {
  id: "d1",
  session_id: "s1",
  source: "tool",
  filename: "报告.docx",
  mime_type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  size_bytes: 4096,
  created_at: "2026-09-17T00:00:00Z",
};

test("docx 产物走预览接口并渲染进 sandbox iframe", async () => {
  mockState.artifacts = [DOCX_ARTIFACT];
  mockState.body = "<h1>报告</h1><p>正文</p>";
  render(<ArtifactPanel sessionId="s1" onClose={vi.fn()} />);
  // 预览异步取回 HTML 后才挂载 iframe；列表项与预览头部也用 title 标注文件名，
  // 因此按 iframe 选择器等待，而不是用 findByTitle（它会先命中列表按钮）
  const frame = await waitFor(() => {
    const el = document.querySelector("iframe");
    expect(el).not.toBeNull();
    return el as HTMLIFrameElement;
  });
  expect(frame.getAttribute("title")).toBe("报告.docx");
  expect(frame.getAttribute("sandbox")).toBe("");
  expect(frame.getAttribute("srcdoc")).toContain("正文");
  await waitFor(() =>
    expect(mockState.fetchedUrls).toContain("/api/v1/artifacts/d1/preview"),
  );
});

test("docx 预览失败时提示错误", async () => {
  mockState.artifacts = [DOCX_ARTIFACT];
  mockState.status = 415;
  render(<ArtifactPanel sessionId="s1" onClose={vi.fn()} />);
  expect(await screen.findByText(/加载失败（HTTP 415）/)).toBeInTheDocument();
});

test("拖拽手柄调整产物区宽度并持久化，双击恢复默认", () => {
  mockState.artifacts = [MARKDOWN_ARTIFACT];
  mockState.body = "# 会议纪要";
  render(<ArtifactPanel sessionId="s1" onClose={vi.fn()} />);

  const panel = screen.getByRole("complementary", { name: "会话产物" });
  const handle = screen.getByTestId("artifact-resize-handle");
  expect(panel).toHaveStyle({ width: "384px" });

  // 手柄在左边缘：往左拖 100px → 面板加宽 100px
  fireEvent.pointerDown(handle, { clientX: 500 });
  fireEvent.pointerMove(window, { clientX: 400 });
  fireEvent.pointerUp(window);
  expect(panel).toHaveStyle({ width: "484px" });
  expect(localStorage.getItem("artifact-panel-width")).toBe("484");

  // 往右猛拖 → 钳制到最小 280px
  fireEvent.pointerDown(handle, { clientX: 500 });
  fireEvent.pointerMove(window, { clientX: 900 });
  fireEvent.pointerUp(window);
  expect(panel).toHaveStyle({ width: "280px" });

  fireEvent.doubleClick(handle);
  expect(panel).toHaveStyle({ width: "384px" });
});
