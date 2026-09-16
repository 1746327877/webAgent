"""本地 faster-whisper 封装：模型懒加载 + 繁体转简体。

模型默认 `Systran/faster-whisper-large-v3`（HF 缓存里已下载，离线可用）。
冷启动要读约 3GB 模型，因此用进程内单例，绝不能每次调用都加载。
"""

from __future__ import annotations

import io
import threading

from src.config import settings
from src.logger import get_logger

logger = get_logger("voice2text.asr")

_model = None
_lock = threading.Lock()
_cc = None


def _simplify(text: str) -> str:
    """繁体转简体；opencc 未安装时原样返回，不阻塞转写。"""
    global _cc
    try:
        from opencc import OpenCC
    except ImportError:
        return text
    if _cc is None:
        _cc = OpenCC("t2s")
    return _cc.convert(text)


def get_model():
    """懒加载单例。"""
    global _model
    with _lock:
        if _model is None:
            from faster_whisper import WhisperModel

            logger.info("加载 Whisper 模型 %s（device=%s, compute=%s）", settings.WHISPER_MODEL, settings.WHISPER_DEVICE, settings.WHISPER_COMPUTE_TYPE)
            _model = WhisperModel(
                settings.WHISPER_MODEL,
                device=settings.WHISPER_DEVICE,
                compute_type=settings.WHISPER_COMPUTE_TYPE,
            )
    return _model


def model_info() -> dict:
    return {
        "model": settings.WHISPER_MODEL,
        "device": settings.WHISPER_DEVICE,
        "compute_type": settings.WHISPER_COMPUTE_TYPE,
        "language": settings.WHISPER_LANGUAGE,
        "loaded": _model is not None,
    }


def transcribe_source(source: str | bytes | io.BytesIO, filename: str = "audio.bin") -> str:
    """转写本地路径 / 内存字节 / 文件对象，返回简体中文文本。

    注意：faster-whisper 只接受路径 / 文件对象 / ndarray，**不接受裸 bytes**
    （会把 bytes 当文件对象而报 `no read() method`），所以这里统一包成 BytesIO。
    """
    if isinstance(source, (bytes, bytearray)):
        source = io.BytesIO(bytes(source))
    segments, _info = get_model().transcribe(
        source,
        language=settings.WHISPER_LANGUAGE or None,
        beam_size=settings.WHISPER_BEAM_SIZE,
        vad_filter=True,  # 去静音：长静音段在 CPU 上纯属浪费
    )
    return _simplify("".join(segment.text for segment in segments).strip())
