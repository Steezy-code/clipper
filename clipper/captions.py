"""Stage 4 - the captions. Word-by-word highlight (the active word pops)."""
from __future__ import annotations
import subprocess
from pathlib import Path
from .config import Config


def _ass_color(hex_str: str) -> str:
    """#RRGGBB -> ASS &HAABBGGRR (opaque)."""
    h = hex_str.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H00{b}{g}{r}".upper()


def _ts(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _safe(word: str) -> str:
    return word.replace("{", "(").replace("}", ")").replace("\n", " ")


def _lines(words: list[dict], cfg: Config) -> list[list[dict]]:
    """Group words into short caption lines, breaking on pauses."""
    lines, cur = [], []
    for w in words:
        if cur:
            gap = w["start"] - cur[-1]["end"]
            if len(cur) >= cfg.words_per_caption or gap > cfg.caption_gap_s:
                lines.append(cur)
                cur = []
        cur.append(w)
    if cur:
        lines.append(cur)
    return lines


def _events(words: list[dict], cfg: Config) -> list[str]:
    accent = _ass_color(cfg.accent_hex)
    out = []
    for line in _lines(words, cfg):
        tokens = [_safe(w["word"]) for w in line]
        for i, w in enumerate(line):
            start = w["start"]
            end = line[i + 1]["start"] if i + 1 < len(line) else w["end"]
            parts = []
            for j, tok in enumerate(tokens):
                if j == i:
                    parts.append(f"{{\\c{accent}\\fscx115\\fscy115\\b1}}{tok}{{\\r}}")
                else:
                    parts.append(tok)
            text = " ".join(parts)
            out.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Pop,,0,0,0,,{text}")
    return out


def write_ass(words: list[dict], path: str, cfg: Config) -> str:
    base = _ass_color(cfg.base_hex)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {cfg.target_w}
PlayResY: {cfg.target_h}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV
Style: Pop,{cfg.font_name},{cfg.font_size},{base},&H00000000,&H64000000,1,1,6,3,2,80,80,260

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(header + "\n".join(_events(words, cfg)) + "\n", encoding="utf-8")
    return path


def burn(video_path: str, ass_path: str, dst: str, cfg: Config) -> str:
    """Burn the ASS karaoke captions into the video."""
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    escaped = ass_path.replace("\\", "/").replace(":", "\\:")
    subprocess.run(
        ["ffmpeg", "-y", "-i", video_path, "-vf", f"ass='{escaped}'",
         "-c:v", cfg.video_codec, "-pix_fmt", "yuv420p", "-c:a", "copy", dst],
        capture_output=True, check=True,
    )
    return dst
