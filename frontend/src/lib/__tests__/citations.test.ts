import { expect, test } from "vitest";
import { linkifyCitations } from "@/lib/citations";

test("只转换存在的引用编号", () => {
  const out = linkifyCitations("并发要点[1]，锁[2]，越界[9]", 2);
  expect(out).toContain("[1](#cite-1)");
  expect(out).toContain("[2](#cite-2)");
  expect(out).toContain("[9]");
  expect(out).not.toContain("#cite-9");
});
