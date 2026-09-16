import { mapPlainText } from "@/lib/plainText";

export interface Citation {
  ref: number;
  chunk_id: string;
  source: string;
  page: number | null;
  score: number;
  snippet: string;
}

function replaceRefs(text: string, maxRef: number): string {
  return text.replace(/\[(\d+)\]/g, (whole, n: string) => {
    const ref = Number(n);
    return ref >= 1 && ref <= maxRef ? `[${n}](#cite-${n})` : whole;
  });
}

/** 把普通文本中的 [n] 转为 #cite-n 锚点；围栏/行内代码块跳过，越界编号不转换 */
export function linkifyCitations(content: string, maxRef: number): string {
  return mapPlainText(content, (text) => replaceRefs(text, maxRef));
}
