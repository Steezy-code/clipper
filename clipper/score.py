"""Stage 2 - the editor. Ollama reads the transcript and picks the best moments."""
from __future__ import annotations
import json
import requests
from .config import Config

_SYSTEM = (
    "You are a sharp short-form video editor. You are given a timestamped transcript. "
    "Pick the {n} strongest standalone moments to cut as vertical shorts. "
    "Each clip must START and END on a natural sentence boundary, make sense without "
    "surrounding context, and run between {lo:.0f} and {hi:.0f} seconds. Favor a strong "
    "hook in the first seconds, a complete thought, and a clear payoff. "
    "Also write a punchy <=8 word on-screen headline ('hook') and a 'score' from 0-100 "
    "predicting its short-form virality. "
    "Return STRICT JSON only, no prose, in this exact shape:\n"
    '{{"clips":[{{"start":<seconds>,"end":<seconds>,"title":"<=6 words",'
    '"hook":"<=8 words","reason":"why it lands","score":<integer 0-100>}}]}}'
)


def _timed_block(words: list[dict], chunk: int = 12) -> str:
    """Compact timestamped transcript: each line prefixed with its start time."""
    lines, buf, t0 = [], [], None
    for w in words:
        if t0 is None:
            t0 = w["start"]
        buf.append(w["word"])
        if len(buf) >= chunk:
            lines.append(f"[{t0:7.2f}] {' '.join(buf)}")
            buf, t0 = [], None
    if buf:
        lines.append(f"[{t0:7.2f}] {' '.join(buf)}")
    return "\n".join(lines)


def _coerce(raw: str) -> list[dict]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end == -1:
            return []
        try:
            data = json.loads(raw[start:end + 1])
        except json.JSONDecodeError:
            return []
    return data.get("clips", []) if isinstance(data, dict) else []


def _clean(clips: list[dict], duration: float, cfg: Config) -> list[dict]:
    out = []
    for c in clips:
        try:
            s, e = float(c["start"]), float(c["end"])
        except (KeyError, TypeError, ValueError):
            continue
        s, e = max(0.0, s), min(duration, e)
        if e - s < cfg.min_clip_s:
            continue
        if e - s > cfg.max_clip_s:
            e = s + cfg.max_clip_s
        try:
            sc = int(float(c.get("score", 50)))
        except (TypeError, ValueError):
            sc = 50
        sc = max(0, min(100, sc))
        title = str(c.get("title", "Clip"))[:60]
        hook = str(c.get("hook") or title)[:80]
        out.append({"start": round(s, 2), "end": round(e, 2),
                    "title": title, "hook": hook,
                    "reason": str(c.get("reason", ""))[:200], "score": sc})
    out.sort(key=lambda c: c["start"])
    # drop overlaps, keep the earlier
    deduped: list[dict] = []
    for c in out:
        if deduped and c["start"] < deduped[-1]["end"]:
            continue
        deduped.append(c)
    deduped.sort(key=lambda c: c["score"], reverse=True)
    return deduped[: cfg.num_clips]


def score(transcript: dict, cfg: Config) -> list[dict]:
    prompt = (
        _SYSTEM.format(n=cfg.num_clips, lo=cfg.min_clip_s, hi=cfg.max_clip_s)
        + "\n\nTRANSCRIPT:\n" + _timed_block(transcript["words"])
    )
    last_err = None
    for attempt in range(2):
        try:
            resp = requests.post(
                f"{cfg.ollama_url}/api/generate",
                # think=False: qwen3 et al. are reasoning models; with format=json the
                # grammar starts at token 0 and collides with the think step, yielding "{}".
                json={"model": cfg.model, "prompt": prompt, "stream": False,
                      "format": "json", "think": False,
                      "options": {"temperature": 0.4 + 0.2 * attempt}},
                timeout=900,
            )
            resp.raise_for_status()
            clips = _clean(_coerce(resp.json().get("response", "")),
                           transcript["duration"], cfg)
            if clips:
                return clips
        except requests.RequestException as exc:
            last_err = exc
    if last_err:
        raise RuntimeError(f"Could not reach Ollama at {cfg.ollama_url}: {last_err}")
    return []
