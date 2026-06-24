"""Layout compositing - vertical split: talking head stacked over a background clip."""
from __future__ import annotations
import subprocess
from pathlib import Path
from .config import Config
from .ffmpeg_util import even


def split_dims(target_w: int, target_h: int, ratio: float) -> tuple[int, int]:
    """(top_h, bottom_h) for a vertical split: both even, summing to target_h.

    ratio is the talking-head (top) fraction, clamped to a sane range.
    """
    ratio = min(0.9, max(0.1, ratio))
    top_h = even(int(target_h * ratio))
    bottom_h = target_h - top_h
    if bottom_h % 2:                 # target_h is even, so nudge if rounding broke parity
        top_h -= 1
        bottom_h += 1
    return top_h, bottom_h


def compose_split(head_path: str, bg_path: str, ass_path: str, dst: str,
                  cfg: Config, bottom_h: int) -> str:
    """Stack head (top) over a looped, cover-cropped background (bottom); burn captions
    over the full frame; keep only the head's audio."""
    esc = ass_path.replace("\\", "/").replace(":", "\\:")
    fc = (f"[0:v]setsar=1[hd];"
          f"[1:v]scale={cfg.target_w}:{bottom_h}:force_original_aspect_ratio=increase,"
          f"crop={cfg.target_w}:{bottom_h},setsar=1[bg];"
          f"[hd][bg]vstack=inputs=2[stk];[stk]ass='{esc}'[v]")
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-i", head_path, "-stream_loop", "-1", "-i", bg_path,
         "-filter_complex", fc, "-map", "[v]", "-map", "0:a?",
         "-c:v", cfg.video_codec, "-pix_fmt", "yuv420p", "-c:a", "aac",
         "-shortest", "-movflags", "+faststart", dst],
        capture_output=True, check=True,
    )
    return dst
