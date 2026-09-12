export default function JsonTree({ data, name, depth = 0 }: { data: unknown; name?: string; depth?: number }) {
  if (data === null || typeof data !== "object") {
    return (
      <p className="whitespace-pre-wrap break-all text-xs">
        {name ? `${name}: ` : ""}
        {JSON.stringify(data) ?? String(data)}
      </p>
    );
  }
  const entries = Object.entries(data as Record<string, unknown>);
  return (
    <details open={depth === 0} className="pl-3 text-xs">
      <summary className="cursor-pointer">
        {name ?? "root"} {Array.isArray(data) ? `[${entries.length}]` : `{${entries.length}}`}
      </summary>
      {entries.map(([k, v]) => (
        <JsonTree key={k} data={v} name={k} depth={depth + 1} />
      ))}
    </details>
  );
}
