export interface DateGroup<T> {
  label: string;
  items: T[];
}

export function groupByDate<T extends { created_at: string; last_message_at?: string | null }>(
  items: T[],
  now: Date = new Date(),
): DateGroup<T>[] {
  const day = 86_400_000;
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const groups: DateGroup<T>[] = [
    { label: "今天", items: [] },
    { label: "昨天", items: [] },
    { label: "7 天内", items: [] },
    { label: "更早", items: [] },
  ];
  for (const item of items) {
    const ts = new Date(item.last_message_at ?? item.created_at).getTime();
    if (ts >= startOfToday) groups[0].items.push(item);
    else if (ts >= startOfToday - day) groups[1].items.push(item);
    else if (ts >= startOfToday - 7 * day) groups[2].items.push(item);
    else groups[3].items.push(item);
  }
  return groups.filter((g) => g.items.length > 0);
}
