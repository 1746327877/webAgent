"""本地 faster-whisper 封装：模型懒加载 + 繁体转简体。

模型默认 `Systran/faster-whisper-large-v3`（HF 缓存里已下载，离线可用）。
冷启动要读约 3GB 模型，因此用进程内单例，绝不能每次调用都加载。
"""

from __future__ import annotations

import io
import os
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

            _enable_cuda_dlls()
            logger.info("加载 Whisper 模型 %s（device=%s, compute=%s）", settings.WHISPER_MODEL, settings.WHISPER_DEVICE, settings.WHISPER_COMPUTE_TYPE)
            _model = WhisperModel(
                settings.WHISPER_MODEL,
                device=settings.WHISPER_DEVICE,
                compute_type=settings.WHISPER_COMPUTE_TYPE,
            )
    return _model


# Windows 上 ctranslate2 需要能找到 CUDA 运行库（cublas64_12 / cudnn64_9 等）。
# 这些 DLL 由 pip 包 nvidia-*-cu12 提供，落在 site-packages/nvidia/*/bin，
# 不在默认 DLL 搜索路径里，因此显式 add_dll_directory（句柄必须保持存活）。
_cuda_dll_handles: list = []


def _enable_cuda_dlls() -> None:
    """让 ctranslate2 能找到 CUDA 运行库（cublas64_12 / cublasLt64_12 / cudnn64_9）。

    两个来源：`WHISPER_CUDA_DLL_DIRS` 显式指定（例如复用 Ollama 自带的 CUDA 库，
    省掉 1.3GB 的 pip 包），以及 pip 包 `nvidia-*-cu12` 落在 site-packages/nvidia/*/bin。

    **只调 `os.add_dll_directory` 不够**：ctranslate2.dll 用普通 LoadLibrary 解析依赖，
    走的是标准搜索顺序（含 PATH），因此这里同时把它们前置进 PATH。
    """
    if os.name != "nt" or not settings.WHISPER_DEVICE.lower().startswith("cuda"):
        return

    import site
    from pathlib import Path

    dirs: list[Path] = []
    for raw in (settings.WHISPER_CUDA_DLL_DIRS or "").split(";"):
        if raw.strip():
            dirs.append(Path(raw.strip()))
    for site_dir in site.getsitepackages() + [site.getusersitepackages()]:
        nvidia_root = Path(site_dir) / "nvidia"
        if nvidia_root.is_dir():
            dirs.extend(sorted(nvidia_root.glob("*/bin")))

    existing = [entry for entry in dirs if entry.is_dir()]
    if not existing:
        return

    os.environ["PATH"] = ";".join(str(d) for d in existing) + ";" + os.environ.get("PATH", "")
    for directory in existing:
        try:
            _cuda_dll_handles.append(os.add_dll_directory(str(directory)))
        except OSError:
            # 不支持 add_dll_directory 时忽略：PATH 已经覆盖
            continue
    logger.info("CUDA DLL 目录已加入搜索路径：%s", [str(d) for d in existing])


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
