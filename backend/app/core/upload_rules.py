"""上传文件的通用校验规则。

附件（api/v1/attachments.py）与智能体头像（api/v1/agents.py）共用同一套
图片类型 / 魔数规则，避免两处各写一份。
"""

IMAGE_EXTS = {"png", "jpg", "jpeg", "webp"}

MIME_BY_EXT = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "pdf": "application/pdf",
    "md": "text/markdown",
    "markdown": "text/markdown",
    "txt": "text/plain",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

# 魔数前缀粗校验：扩展名与实际内容明显不符时拒绝（不做完整图片解码）
MAGIC_PREFIXES = {
    "png": (b"\x89PNG",),
    "jpg": (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
    "webp": (b"RIFF",),
}


def has_valid_image_magic(content: bytes, ext: str) -> bool:
    """扩展名属于图片时，校验文件头魔数；非图片扩展名一律 False。"""
    prefixes = MAGIC_PREFIXES.get(ext)
    if prefixes is None:
        return False
    return any(content.startswith(prefix) for prefix in prefixes)
