"""本地 faster-whisper 封装：模型懒加载 + 繁体转简体。

设计见 `docs/设计/23-语音转写MCP.md`。模型默认用 HuggingFace 上的
`Systran/faster-whisper-large-v3`（可用 WHISPER_MODEL 覆盖；本机缓存里已有
large-v3 与 base，离线也能加载）。
"""

from __future__ import annotations

import io
import os
import threading

MODEL_NAME = os.getenv("WHISPER_MODEL", "Systran/faster-whisper-large-v3")
DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
LANGUAGE = os.getenv("WHISPER_LANGUAGE", "zh")
BEAM_SIZE = int(os.getenv("WHISPER_BEAM_SIZE", "5"))

_model = None
_lock = threading.Lock()


def _simplify(text: str) -> str:
    """繁体转简体（opencc 缺失时原样返回，不阻塞转写）。"""
    try:
        from opencc import OpenCC
    except ImportError:
        return text
    global _cc
    try:
        _cc
    except NameError:
        _cc = OpenCC("t2s")
    return _cc.convert(text)


def get_model():
    """懒加载单例：Whisper large-v3 冷启动需要读 3GB 模型，不能每次调用都加载。"""
    global _model
    with _lock:
        if _model is None:
            from faster_whisper import WhisperModel

            _model = WhisperModel(MODEL_NAME, device=DEVICE, compute_type=COMPUTE_TYPE)
    return _model


def model_info() -> dict:
    return {
        "model": MODEL_NAME,
        "device": DEVICE,
        "compute_type": COMPUTE_TYPE,
        "language": LANGUAGE,
        "loaded": _model is not None,
    }


def transcribe_source(source: str | bytes | io.BytesIO, filename: str = "audio.bin") -> str:
    """转写本地路径或内存中的音频字节，返回简体中文文本。

    注意：faster-whisper 只接受路径 / 文件对象 / ndarray，**不接受裸 bytes**
    （传 bytes 会被当成文件对象而报 "no read() method"），因此这里统一包成 BytesIO。
    """
    if isinstance(source, (bytes, bytearray)):
        source = io.BytesIO(bytes(source))
    segments, _info = get_model().transcribe(
        source,
        language=LANGUAGE or None,
        beam_size=BEAM_SIZE,
        vad_filter=True,  # 去静音，避免长静音段拖慢 CPU 推理
    )
    return _simplify("".join(segment.text for segment in segments).strip())
