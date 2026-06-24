"""Stage 1 - the listener. faster-whisper gives word-level timestamps."""
from __future__ import annotations
import os
import sys
import sysconfig
from pathlib import Path
from .config import Config


def _add_cuda_dlls() -> None:
    # ponytail: Windows only. ctranslate2 loads cuBLAS/cuDNN via plain LoadLibrary, which
    # only searches PATH - not add_dll_directory - so prepend the pip `nvidia-*-cu12`
    # wheels' bin dirs to PATH. Harmless if the wheels aren't installed.
    if sys.platform != "win32":
        return
    nvidia = Path(sysconfig.get_paths()["purelib"]) / "nvidia"
    dirs = [str(nvidia / sub / "bin") for sub in ("cublas", "cudnn")
            if (nvidia / sub / "bin").is_dir()]
    if dirs:
        os.environ["PATH"] = os.pathsep.join(dirs + [os.environ.get("PATH", "")])


def _resolve_device(cfg: Config) -> tuple[str, str]:
    if cfg.whisper_device != "auto":
        compute = cfg.whisper_compute if cfg.whisper_device == "cuda" else "int8"
        return cfg.whisper_device, compute
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda", cfg.whisper_compute
    except Exception:
        pass
    return "cpu", "int8"


def transcribe(media_path: str, cfg: Config) -> dict:
    """Return {'words': [{word,start,end}], 'text': str, 'duration': float}."""
    from faster_whisper import WhisperModel

    device, compute = _resolve_device(cfg)
    if device == "cuda":
        _add_cuda_dlls()
    model = WhisperModel(cfg.whisper_model, device=device, compute_type=compute)
    segments, info = model.transcribe(media_path, word_timestamps=True, vad_filter=True)

    words: list[dict] = []
    text_parts: list[str] = []
    for seg in segments:
        text_parts.append(seg.text.strip())
        for w in (seg.words or []):
            token = w.word.strip()
            if token:
                words.append({"word": token, "start": float(w.start), "end": float(w.end)})

    return {"words": words, "text": " ".join(text_parts).strip(), "duration": float(info.duration)}
