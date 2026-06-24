"""Central configuration. Everything tunable lives here or in env vars."""
from __future__ import annotations
import os
from dataclasses import dataclass


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.environ[key])
    except (KeyError, ValueError):
        return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ[key])
    except (KeyError, ValueError):
        return default


@dataclass
class Config:
    # --- Ollama (the "editor" that picks clips) ---
    ollama_url: str = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    model: str = os.environ.get("CLIPPER_MODEL", "qwen3:14b")  # 8b also fine; 14b = better taste, fits a 12GB card

    # --- Whisper (the "listener") ---
    # base.en = fast, small.en = better, medium.en / large-v3 = best (needs more VRAM).
    whisper_model: str = os.environ.get("WHISPER_MODEL", "small.en")
    whisper_compute: str = os.environ.get("WHISPER_COMPUTE", "int8")
    whisper_device: str = os.environ.get("WHISPER_DEVICE", "auto")  # auto|cuda|cpu

    # --- Clip selection ---
    num_clips: int = _env_int("NUM_CLIPS", 6)
    min_clip_s: float = _env_float("MIN_CLIP_S", 15.0)
    max_clip_s: float = _env_float("MAX_CLIP_S", 60.0)

    # --- Reframe / face tracking ---
    target_w: int = _env_int("TARGET_W", 1080)   # output width  (9:16)
    target_h: int = _env_int("TARGET_H", 1920)   # output height
    detect_every: int = _env_int("DETECT_EVERY", 3)   # run face detect every N frames
    smooth_alpha: float = _env_float("SMOOTH_ALPHA", 0.12)  # lower = smoother/laggier

    # --- Captions ---
    accent_hex: str = os.environ.get("ACCENT_HEX", "#FF5C38")  # active word color
    base_hex: str = os.environ.get("BASE_HEX", "#FFFFFF")      # inactive words
    words_per_caption: int = _env_int("WORDS_PER_CAPTION", 4)
    caption_gap_s: float = _env_float("CAPTION_GAP_S", 0.6)    # break line on pauses
    font_name: str = os.environ.get("FONT_NAME", "Arial")
    font_size: int = _env_int("FONT_SIZE", 120)

    # --- Encoding ---
    use_nvenc: bool = os.environ.get("USE_NVENC", "1") == "1"

    # --- Paths ---
    work_dir: str = os.environ.get("WORK_DIR", "work")
    out_dir: str = os.environ.get("OUT_DIR", "clips")

    @property
    def video_codec(self) -> str:
        return "h264_nvenc" if self.use_nvenc else "libx264"
