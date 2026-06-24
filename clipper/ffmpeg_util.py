"""Small wrappers around ffmpeg / ffprobe. No business logic here."""
from __future__ import annotations
import json
import shutil
import subprocess
from pathlib import Path


def ensure_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise RuntimeError(
            "ffmpeg/ffprobe not found on PATH. Install ffmpeg and reopen your shell.\n"
            "  Windows : winget install Gyan.FFmpeg\n"
            "  macOS   : brew install ffmpeg\n"
            "  Linux   : sudo apt install ffmpeg"
        )


def probe(path: str) -> dict:
    """Return {width, height, fps, duration} for the first video stream."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_streams", "-show_format", path],
        capture_output=True, text=True, check=True,
    ).stdout
    data = json.loads(out)
    vstream = next(s for s in data["streams"] if s["codec_type"] == "video")
    num, den = (vstream.get("r_frame_rate", "30/1").split("/") + ["1"])[:2]
    fps = float(num) / float(den or 1)
    return {
        "width": int(vstream["width"]),
        "height": int(vstream["height"]),
        "fps": fps if fps > 0 else 30.0,
        "duration": float(data["format"]["duration"]),
    }


def cut(src: str, start: float, end: float, dst: str, codec: str = "libx264") -> str:
    """Cut [start, end] into its own file, re-encoding so the timeline is clean.

    Pass the GPU codec (h264_nvenc) to keep this off the CPU when a GPU is present.
    """
    preset = ["-preset", "fast"] if "nvenc" in codec else ["-preset", "veryfast"]
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", src,
         "-c:v", codec, *preset, "-c:a", "aac", "-movflags", "+faststart", dst],
        capture_output=True, check=True,
    )
    return dst


def cut_spans(src: str, start: float, end: float, rel_spans: list[tuple[float, float]],
              dst: str, codec: str = "libx264") -> str:
    """Cut [start, end] keeping only rel_spans (clip-relative), concatenated - used to drop
    silence. Fast input seek to the clip window first, so only the clip is decoded; trim +
    concat keep audio and video sample-accurate.
    """
    preset = ["-preset", "fast"] if "nvenc" in codec else ["-preset", "veryfast"]
    parts = []
    for i, (a, b) in enumerate(rel_spans):
        parts.append(f"[0:v]trim={a:.3f}:{b:.3f},setpts=PTS-STARTPTS[v{i}]")
        parts.append(f"[0:a]atrim={a:.3f}:{b:.3f},asetpts=PTS-STARTPTS[a{i}]")
    n = len(rel_spans)
    parts.append("".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[v][a]")
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-ss", f"{start:.3f}", "-i", src, "-t", f"{end - start:.3f}",
         "-filter_complex", ";".join(parts), "-map", "[v]", "-map", "[a]",
         "-c:v", codec, *preset, "-c:a", "aac", "-movflags", "+faststart", dst],
        capture_output=True, check=True,
    )
    return dst


def even(n: int) -> int:
    """h264 needs even dimensions."""
    n = int(round(n))
    return n if n % 2 == 0 else n + 1
