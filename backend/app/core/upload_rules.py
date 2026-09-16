"""上传文件的通用校验规则。

附件（api/v1/attachments.py）与智能体头像（api/v1/agents.py）共用同一套
图片类型 / 魔数规则，避免两处各写一份。
"""

IMAGE_EXTS = {"png", "jpg", "jpeg", "webp"}

AUDIO_EXTS = {"mp3", "wav", "m4a", "mp4", "aac", "flac", "ogg", "webm", "amr"}

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
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "m4a": "audio/mp4",
    "mp4": "audio/mp4",
    "aac": "audio/aac",
    "flac": "audio/flac",
    "ogg": "audio/ogg",
    "webm": "audio/webm",
    "amr": "audio/amr",
}

# 魔数前缀粗校验：扩展名与实际内容明显不符时拒绝（不做完整图片解码）
MAGIC_PREFIXES = {
    "png": (b"\x89PNG",),
    "jpg": (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
    "webp": (b"RIFF",),
}

# 音频魔数 (偏移量, 魔数)。浏览器录制的 webm 常被改名成 .mp3，因此只要求
# "命中任一已知音频签名"，不要求与扩展名一一对应。
AUDIO_MAGIC: tuple[tuple[int, bytes], ...] = (
    (4, b"ftypM4A "),  # m4a：比 mp4 更具体，放前面
    (4, b"ftyp"),  # mp4 / m4a
    (0, b"RIFF"),  # wav
    (0, b"FORM"),  # aiff
    (0, b"fLaC"),  # flac
    (0, b"OggS"),  # ogg
    (0, b"ID3"),  # mp3（带 ID3 标签）
    (0, b"\x1a\x45\xdf\xa3"),  # webm / mkv
    (0, b"\xff\xf1"),  # aac ADTS
    (0, b"\xff\xf9"),  # aac ADTS（另一种）
    (0, b"#!AMR"),  # amr
)


def has_valid_image_magic(content: bytes, ext: str) -> bool:
    """扩展名属于图片时，校验文件头魔数；非图片扩展名一律 False。"""
    prefixes = MAGIC_PREFIXES.get(ext)
    if prefixes is None:
        return False
    return any(content.startswith(prefix) for prefix in prefixes)


def has_valid_audio_magic(content: bytes, ext: str) -> bool:
    """扩展名属于音频时，校验文件头是否命中已知音频签名；非音频一律 False。

    只认"是某种音频"，不校验扩展名与真实格式一致——改名很常见（webm → .mp3）。
    """
    if ext not in AUDIO_EXTS:
        return False
    for offset, magic in AUDIO_MAGIC:
        if len(content) >= offset + len(magic) and content[offset : offset + len(magic)] == magic:
            return True
    return False
