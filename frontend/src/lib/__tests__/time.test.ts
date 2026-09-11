import { expect, test } from "vitest";
import { groupByDate } from "@/lib/time";

const now = new Date("2026-09-11T12:00:00+08:00");
const mk = (id: string, iso: string) => ({ id, created_at: iso, last_message_at: iso });

test("按今天/昨天/7天内/更早分组", () => {
  const groups = groupByDate(
    [
      mk("a", "2026-09-11T10:00:00+08:00"),
      mk("b", "2026-09-10T10:00:00+08:00"),
      mk("c", "2026-09-08T10:00:00+08:00"),
      mk("d", "2026-08-01T10:00:00+08:00"),
    ],
    now,
  );
  expect(groups.map((g) => g.label)).toEqual(["今天", "昨天", "7 天内", "更早"]);
  expect(groups[0].items.map((i) => i.id)).toEqual(["a"]);
});

test("空组被过滤", () => {
  const groups = groupByDate([mk("a", "2026-09-11T10:00:00+08:00")], now);
  expect(groups).toHaveLength(1);
});

test("无 last_message_at 时回退 created_at", () => {
  const groups = groupByDate(
    [{ id: "x", created_at: "2026-09-10T10:00:00+08:00", last_message_at: null }],
    now,
  );
  expect(groups[0].label).toBe("昨天");
});
