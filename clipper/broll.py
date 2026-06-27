"""Auto B-roll: cut to relevant Pexels stock video on keyword moments.

Pure helpers (keywords, pick_file) are unit-tested; fetching needs PEXELS_API_KEY and
hits the network (failures degrade to "no cutaway"); add_broll does the ffmpeg overlay.
"""
from __future__ import annotations
import json
import re
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path
from .config import Config

_SEARCH = "https://api.pexels.com/videos/search"
_STOP = {"the", "a", "an", "and", "or", "but", "to", "of", "in", "on", "for", "is", "are",
         "it", "this", "that", "you", "your", "we", "they", "with", "as", "at", "be", "do",
         "does", "not", "so", "just", "like", "have", "has", "about", "into", "really",
         "going", "because", "there", "their", "what", "when", "then", "than", "them"}


def have_key(cfg: Config) -> bool:
    return bool(cfg.pexels_key)


def keywords(words: list[dict], cfg: Config) -> list[tuple[str, float]]:
    """Pick up to broll_max content words (term, start_time) spaced >= broll_gap apart."""
    out: list[tuple[str, float]] = []
    last = -1e9
    seen: set[str] = set()
    for w in words:
        term = re.sub(r"[^a-zA-Z]", "", w["word"]).lower()
        if len(term) < 5 or term in _STOP or term in seen:
            continue
        if w["start"] - last < cfg.broll_gap:
            continue
        out.append((term, w["start"]))
        seen.add(term)
        last = w["start"]
        if len(out) >= cfg.broll_max:
            break
    return out


def pick_file(video: dict) -> str | None:
    """From a Pexels video result, choose the best file link: prefer portrait, height
    closest to 1920 but not enormous. Returns a URL or None."""
    files = video.get("video_files") or []
    if not files:
        return None
    def key(f):
        w, h = f.get("width") or 0, f.get("height") or 0
        portrait = 1 if h >= w else 0
        return (portrait, -abs((h or 0) - 1920))
    return max(files, key=key).get("link")


def _search(term: str, cfg: Config) -> dict | None:
    url = f"{_SEARCH}?query={urllib.parse.quote(term)}&orientation=portrait&per_page=3&size=medium"
    req = urllib.request.Request(url, headers={"Authorization": cfg.pexels_key})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except Exception:
        return None


def _slug(term: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", term.lower()).strip("-") or "broll"


def fetch(term: str, cfg: Config, cache: Path) -> tuple[str, dict] | None:
    """Download a stock clip for `term` (cached by term). Returns (path, credit) or None."""
    cache.mkdir(parents=True, exist_ok=True)
    dst = cache / f"{_slug(term)}.mp4"
    data = _search(term, cfg)
    if not data or not data.get("videos"):
        return None
    video = data["videos"][0]
    credit = {"term": term, "photographer": video.get("user", {}).get("name", "Pexels"),
              "url": video.get("url", "https://pexels.com")}
    if dst.exists() and dst.stat().st_size > 1000:
        return str(dst), credit
    link = pick_file(video)
    if not link:
        return None
    try:
        urllib.request.urlretrieve(link, dst)
    except Exception:
        return None
    return str(dst), credit


def gather(words: list[dict], cfg: Config, cache: Path) -> tuple[list[tuple[str, float, float]], list[dict]]:
    """Resolve keyword moments to (video_path, start, end) cutaways + credits. Skips misses."""
    items, credits = [], []
    for term, t in keywords(words, cfg):
        got = fetch(term, cfg, cache)
        if got:
            path, credit = got
            items.append((path, t, t + cfg.broll_dur))
            credits.append(credit)
    return items, credits


def add_broll(base: str, ass_path: str, items: list[tuple[str, float, float]],
              dst: str, cfg: Config) -> str:
    """Overlay each cutaway full-frame during its window, then burn captions on top.
    base must be the captionless reframed clip; the speaker's audio is kept."""
    W, H = cfg.target_w, cfg.target_h
    inputs = ["-i", base]
    for path, _a, _b in items:
        inputs += ["-i", path]
    parts, prev = [], "[0:v]"
    for i, (_p, a, b) in enumerate(items, start=1):
        parts.append(f"[{i}:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
                     f"crop={W}:{H},setsar=1,setpts=PTS-STARTPTS+{a:.3f}/TB[b{i}]")
        parts.append(f"{prev}[b{i}]overlay=enable='between(t,{a:.3f},{b:.3f})'[o{i}]")
        prev = f"[o{i}]"
    esc = ass_path.replace("\\", "/").replace(":", "\\:")
    parts.append(f"{prev}ass='{esc}'[v]")
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(parts),
         "-map", "[v]", "-map", "0:a?", "-c:v", cfg.video_codec, "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", "-movflags", "+faststart", dst],
        capture_output=True, check=True,
    )
    return dst
