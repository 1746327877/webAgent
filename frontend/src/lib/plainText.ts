/**
 * 逐行遍历 markdown 的「可见文本」，跳过围栏代码块与行内代码。
 *
 * 引用锚点、裸链接这类字面量替换都要走这里：直接对整段 markdown 做正则会
 * 把代码块里的示例也改掉（见 `linkifyCitations` / `autolinkBareUrls`）。
 */
export function mapPlainText(content: string, transform: (text: string) => string): string {
  const fence = /^\s*(```|~~~)/;
  let inFence = false;
  return content
    .split("\n")
    .map((line) => {
      if (fence.test(line)) {
        inFence = !inFence;
        return line;
      }
      if (inFence) return line;
      // 行内代码（`…`，含连续反引号定界）之外才变换；未闭合的反引号后按代码处理
      const parts = line.split(/(`+)/);
      let inCode = false;
      let out = "";
      for (const part of parts) {
        if (part.startsWith("`")) {
          inCode = !inCode;
          out += part;
        } else {
          out += inCode ? part : transform(part);
        }
      }
      return out;
    })
    .join("\n");
}
