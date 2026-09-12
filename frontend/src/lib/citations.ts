export interface Citation {
  ref: number;
  chunk_id: string;
  source: string;
  page: number | null;
  score: number;
  snippet: string;
}

export function linkifyCitations(content: string, maxRef: number): string {
  return content.replace(/\[(\d+)\]/g, (whole, n: string) => {
    const ref = Number(n);
    return ref >= 1 && ref <= maxRef ? `[${n}](#cite-${n})` : whole;
  });
}
