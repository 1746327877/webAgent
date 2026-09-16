const COLORS = [
  "bg-rose-500",
  "bg-amber-500",
  "bg-emerald-500",
  "bg-sky-500",
  "bg-violet-500",
  "bg-fuchsia-500",
  "bg-teal-500",
  "bg-indigo-500",
];

/** 名字首字（按码位取，中文/emoji 都不会被截断成半个字符） */
export function avatarInitial(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return "?";
  return Array.from(trimmed)[0];
}

/** 名字 → 确定性配色，让没有头像的智能体也有稳定辨识度 */
export function avatarColor(name: string): string {
  let hash = 0;
  for (const ch of name) hash = (hash * 31 + (ch.codePointAt(0) ?? 0)) % 997;
  return COLORS[hash % COLORS.length];
}
