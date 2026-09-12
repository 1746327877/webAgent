import { expect, test } from "vitest";
import { linkifyCitations } from "@/lib/citations";

test("只转换存在的引用编号", () => {
  const out = linkifyCitations("并发要点[1]，锁[2]，越界[9]", 2);
  expect(out).toContain("[1](#cite-1)");
  expect(out).toContain("[2](#cite-2)");
  expect(out).toContain("[9]");
  expect(out).not.toContain("#cite-9");
});

test("围栏代码块中的 [n] 不转换", () => {
  const out = linkifyCitations("看代码：\n```\narr[1]\n```\n结论[1]", 1);
  expect(out).toContain("```\narr[1]\n```");
  expect(out).not.toContain("arr[1](#cite-1)");
  expect(out).toContain("结论[1](#cite-1)");
});

test("行内代码中的 [n] 不转换", () => {
  const out = linkifyCitations("例如 `arr[1]`，结论[1]", 1);
  expect(out).toContain("`arr[1]`");
  expect(out).not.toContain("arr[1](#cite-1)");
  expect(out).toContain("结论[1](#cite-1)");
});
