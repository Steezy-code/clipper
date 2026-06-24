"""Stage 4 - the captions. Word-by-word highlight (the active word pops).

The ASS file written here is burned into the video during the reframe encode
(see crop.reframe's ass_path) so there is no separate caption pass.
"""
from __future__ import annotations
from pathlib import Path
from .config import Config


STYLES: dict[str, dict] = {
    # size_mult scales cfg.font_size; border_style 1=outline, 3=opaque box.
    "karaoke": {"size_mult": 1.0, "border_style": 1, "outline": 6, "shadow": 3, "bold": 1},
    "boxed":   {"size_mult": 0.92, "border_style": 3, "outline": 4, "shadow": 0, "bold": 1},
    "bold":    {"size_mult": 1.05, "border_style": 1, "outline": 8, "shadow": 3, "bold": 1},
}

_STOP = {"the", "a", "an", "and", "or", "but", "to", "of", "in", "on", "for", "is",
         "are", "it", "this", "that", "you", "your", "i", "we", "they", "with", "as",
         "at", "be", "do", "does", "not", "so", "just", "like", "have", "has", "my"}


def _emphasis(line: list[dict]) -> set[int]:
    """Indices of up to 2 content words to keep tinted in the accent color."""
    idx = [i for i, w in enumerate(line)
           if len(w["word"].strip(".,!?'\"")) >= 4
           and w["word"].strip(".,!?'\"").lower() not in _STOP]
    return set(idx[:2])


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


def emphasis_times(words: list[dict], cfg: Config) -> list[float]:
    """Start time of the first emphasized keyword in each caption line - the moments a
    punch-in zoom should land on. Same line/emphasis logic the captions use."""
    out = []
    for line in _lines(words, cfg):
        emph = _emphasis(line)
        if emph:
            out.append(line[min(emph)]["start"])
    return out


def _events(words: list[dict], cfg: Config) -> list[str]:
    accent = _ass_color(cfg.accent_hex)
    out = []
    for line in _lines(words, cfg):
        tokens = [_safe(w["word"]) for w in line]
        emph = _emphasis(line)
        for i, w in enumerate(line):
            start = w["start"]
            end = line[i + 1]["start"] if i + 1 < len(line) else w["end"]
            parts = []
            for j, tok in enumerate(tokens):
                if j == i:
                    parts.append(f"{{\\c{accent}\\fscx115\\fscy115\\b1}}{tok}{{\\r}}")
                elif j in emph:
                    parts.append(f"{{\\c{accent}}}{tok}{{\\r}}")
                else:
                    parts.append(tok)
            text = " ".join(parts)
            out.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Pop,,0,0,0,,{text}")
    return out


def write_ass(words: list[dict], path: str, cfg: Config, hook: str = "") -> str:
    base = _ass_color(cfg.base_hex)
    st = STYLES.get(cfg.caption_style, STYLES["karaoke"])
    size = int(cfg.font_size * st["size_mult"])
    hook_size = int(cfg.font_size * 0.7)
    pop = (f"Style: Pop,{cfg.font_name},{size},{base},&H00000000,&H64000000,"
           f"{st['bold']},{st['border_style']},{st['outline']},{st['shadow']},2,80,80,260")
    hook_style = (f"Style: Hook,{cfg.font_name},{hook_size},{base},&H00000000,&H64000000,"
                  f"1,1,5,2,8,60,60,120")
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {cfg.target_w}
PlayResY: {cfg.target_h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV
{pop}
{hook_style}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = _events(words, cfg)
    if hook and words:
        end = words[-1]["end"]
        events = [f"Dialogue: 0,{_ts(0.0)},{_ts(end)},Hook,,0,0,0,,{_safe(hook)}"] + events
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return path
