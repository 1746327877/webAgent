import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import AgentAvatar from "@/components/agents/AgentAvatar";
import { avatarInitial } from "@/lib/avatar";

test("无头像时用名字首字", () => {
  render(<AgentAvatar name="代码专家" className="size-8" />);
  expect(screen.getByText("代")).toBeInTheDocument();
});

test("名字为空时兜底为 ?", () => {
  render(<AgentAvatar name="   " className="size-8" />);
  expect(screen.getByText("?")).toBeInTheDocument();
});

test("有本地预览时直接渲染图片", () => {
  render(<AgentAvatar name="代码专家" previewUrl="blob:preview" className="size-8" />);
  expect(screen.getByAltText("代码专家 头像")).toHaveAttribute("src", "blob:preview");
});

test("avatarInitial 按码位取首字（emoji 不会被截半）", () => {
  expect(avatarInitial("🤖助手")).toBe("🤖");
  expect(avatarInitial("  hello")).toBe("h");
  expect(avatarInitial("")).toBe("?");
});
