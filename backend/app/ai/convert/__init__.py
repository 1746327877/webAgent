"""文档格式转换：pdf/docx/md/txt → md/docx/pdf（见 docs/设计/25）。"""

from dataclasses import dataclass
from pathlib import Path

from app.ai.convert.readers import read_source
from app.ai.convert.writers import to_docx, to_markdown, to_pdf

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MIME_BY_TARGET = {"md": "text/markdown", "docx": DOCX_MIME, "pdf": "application/pdf"}
SOURCE_EXTS = {"pdf", "docx", "md", "markdown", "txt"}
TARGETS = ("md", "docx", "pdf")


class ConvertError(ValueError):
    """转换失败（参数非法、内容为空、依赖报错等）；消息面向用户可读。"""


@dataclass(frozen=True)
class ConvertedDoc:
    data: bytes
    mime: str
    ext: str


def convert_file(path: Path, src_ext: str, target: str) -> ConvertedDoc:
    """把来源文件转换成目标格式字节；失败抛 ConvertError。"""
    src_ext = (src_ext or "").lower()
    target = (target or "").lower().lstrip(".")
    if src_ext not in SOURCE_EXTS:
        raise ConvertError(f"不支持的来源格式：{src_ext or '未知'}")
    if target not in TARGETS:
        raise ConvertError("目标格式仅支持 md / docx / pdf")
    if target == src_ext or (target == "md" and src_ext == "markdown"):
        raise ConvertError(f"源文件已经是 {target} 格式，无需转换")
    if not path.is_file():
        raise ConvertError("源文件不存在")
    try:
        blocks = read_source(path, src_ext)
    except ConvertError:
        raise
    except Exception as exc:  # 外部解析失败统一转为用户可读错误，原始异常由 from 保留在堆栈
        raise ConvertError(f"解析失败：{str(exc)[:200]}") from exc
    if not blocks:
        hint = "（可能是扫描件，未接入 OCR）" if src_ext == "pdf" else ""
        raise ConvertError(f"未提取到可转换的内容{hint}")
    if target == "md":
        data = to_markdown(blocks)
    elif target == "docx":
        data = to_docx(blocks)
    else:
        data = to_pdf(blocks)
    return ConvertedDoc(data=data, mime=MIME_BY_TARGET[target], ext=target)
