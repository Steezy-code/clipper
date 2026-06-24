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
    model: str = os.environ.get("CLIPPER_MODEL", "qwen3:8b")  # 8b = fast; qwen3:14b = better taste, more VRAM

    # --- Whisper (the "listener") ---
    # base.en = fast, small.en = better, medium.en / large-v3 = best (needs more VRAM).
    whisper_model: str = os.environ.get("WHISPER_MODEL", "base.en")
    whisper_compute: str = os.environ.get("WHISPER_COMPUTE", "int8")
    whisper_device: str = os.environ.get("WHISPER_DEVICE", "auto")  # auto|cuda|cpu

    # --- Clip selection ---
    num_clips: int = _env_int("NUM_CLIPS", 6)
    min_clip_s: float = _env_float("MIN_CLIP_S", 15.0)
    max_clip_s: float = _env_float("MAX_CLIP_S", 60.0)

    # --- Silence trimming ---
    trim_silence: bool = os.environ.get("TRIM_SILENCE", "1") == "1"
    silence_max: float = _env_float("SILENCE_MAX", 0.5)    # collapse gaps longer than this
    silence_keep: float = _env_float("SILENCE_KEEP", 0.15)  # pad left around each cut

    # --- Reframe / face tracking ---
    target_w: int = _env_int("TARGET_W", 1080)   # output width  (9:16)
    target_h: int = _env_int("TARGET_H", 1920)   # output height
    detect_every: int = _env_int("DETECT_EVERY", 6)   # run face detect every N frames
    smooth_alpha: float = _env_float("SMOOTH_ALPHA", 0.12)  # lower = smoother/laggier

    # --- Captions ---
    accent_hex: str = os.environ.get("ACCENT_HEX", "#FF5C38")  # active word color
    base_hex: str = os.environ.get("BASE_HEX", "#FFFFFF")      # inactive words
    words_per_caption: int = _env_int("WORDS_PER_CAPTION", 3)
    caption_gap_s: float = _env_float("CAPTION_GAP_S", 0.6)    # break line on pauses
    font_name: str = os.environ.get("FONT_NAME", "Arial")
    font_size: int = _env_int("FONT_SIZE", 120)
    caption_style: str = os.environ.get("CAPTION_STYLE", "karaoke")

    # --- Encoding ---
    use_nvenc: bool = os.environ.get("USE_NVENC", "1") == "1"

    # --- Paths ---
    work_dir: str = os.environ.get("WORK_DIR", "work")
    out_dir: str = os.environ.get("OUT_DIR", "clips")

    @property
    def video_codec(self) -> str:
        return "h264_nvenc" if self.use_nvenc else "libx264"


ASPECTS: dict[str, tuple[int, int]] = {
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "16:9": (1920, 1080),
}
CAPTION_STYLES: tuple[str, ...] = ("karaoke", "boxed", "bold")
# length preset -> (min_clip_s, max_clip_s)
LENGTHS: dict[str, tuple[float, float]] = {
    "auto": (15.0, 60.0),
    "under30": (8.0, 30.0),
    "30to60": (30.0, 60.0),
    "60to90": (60.0, 90.0),
}


def validate_overrides(form: dict) -> dict:
    """Whitelist + clamp UI form fields into Config overrides. Bad values are dropped."""
    out: dict = {}
    if form.get("aspect") in ASPECTS:
        out["target_w"], out["target_h"] = ASPECTS[form["aspect"]]
    if form.get("caption_style") in CAPTION_STYLES:
        out["caption_style"] = form["caption_style"]
    if form.get("length") in LENGTHS:
        out["min_clip_s"], out["max_clip_s"] = LENGTHS[form["length"]]
    if form.get("trim") is not None:
        out["trim_silence"] = form["trim"] == "1"
    n = form.get("num_clips")
    if n is not None:
        try:
            out["num_clips"] = max(1, min(12, int(n)))
        except (TypeError, ValueError):
            pass
    return out
