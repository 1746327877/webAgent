import type { Block } from "@/api/sessions";
import { isHttpUrl } from "@/lib/linkify";

/** 单条消息最多展示几张工具图片，避免把回复撑爆 */
const GALLERY_MAX = 5;

/** 汇总本条消息所有 tool_result 块里的图片：只留 http(s)、去重、限量保序 */
function collectImages(blocks: Block[]): string[] {
  const images: string[] = [];
  for (const block of blocks) {
    if (block.type !== "tool_result" || !Array.isArray(block.images)) continue;
    for (const item of block.images) {
      if (typeof item !== "string" || !isHttpUrl(item)) continue;
      if (!images.includes(item) && images.length < GALLERY_MAX) images.push(item);
    }
  }
  return images;
}

/**
 * 工具产出的图片，附在助手回复下方展示。
 *
 * 不放工具调用卡片里：卡片默认折叠、属于「调用详情」，而图片是用户真正要的**结果**
 * （支付二维码、生成图等），应该在正经回复里直接看到。
 */
export default function ToolArtifacts({ blocks, text }: { blocks: Block[]; text: string }) {
  // 模型自己在回复里用 markdown 图片语法写出来的，下面不重复展示
  const images = collectImages(blocks).filter((url) => !text.includes(url));
  if (images.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-2 pt-1" aria-label="工具返回的图片">
      {images.map((url) => (
        <a
          key={url}
          href={url}
          target="_blank"
          rel="noreferrer noopener"
          title={`${url}（在新标签页打开原图）`}
        >
          {/* object-contain 不裁切（二维码必须完整才能扫），白底保证深色主题下也能扫 */}
          <img
            src={url}
            alt="工具返回图片"
            loading="lazy"
            className="h-32 w-32 rounded-md border bg-white object-contain p-1"
          />
        </a>
      ))}
    </div>
  );
}
