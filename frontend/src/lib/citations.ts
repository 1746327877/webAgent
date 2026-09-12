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

/** 行内代码（`…`，含连续反引号定界）之外才替换；未闭合的反引号后按代码处理 */
function linkifyPlain(text: string, maxRef: number): string {
  const parts = text.split(/(`+)/);
  let inCode = false;
  let out = "";
  for (const part of parts) {
    if (part.startsWith("`")) {
      inCode = !inCode;
      out += part;
    } else {
      out += inCode ? part : replaceRefs(part, maxRef);
    }
  }
  return out;
}

/** 把普通文本中的 [n] 转为 #cite-n 锚点；围栏/行内代码块跳过，越界编号不转换 */
export function linkifyCitations(content: string, maxRef: number): string {
  const fence = /^\s*(```|~~~)/;
  let inFence = false;
  return content
    .split("\n")
    .map((line) => {
      if (fence.test(line)) {
        inFence = !inFence;
        return line;
      }
      return inFence ? line : linkifyPlain(line, maxRef);
    })
    .join("\n");
}
