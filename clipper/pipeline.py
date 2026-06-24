"""Orchestrates the five stages and reports progress as it goes."""
from __future__ import annotations
import re
from pathlib import Path
from typing import Callable

from .config import Config
from . import ffmpeg_util, transcribe, score, crop, captions

Progress = Callable[[int, str], None]


def _slug(text: str, fallback: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return s[:40] or fallback


def _clip_words(words: list[dict], start: float, end: float) -> list[dict]:
    out = []
    for w in words:
        if w["end"] <= start or w["start"] >= end:
            continue
        out.append({"word": w["word"],
                    "start": max(0.0, w["start"] - start),
                    "end": max(0.0, w["end"] - start)})
    return out


def process(media_path: str, cfg: Config, on_progress: Progress = lambda p, m: None) -> list[dict]:
    ffmpeg_util.ensure_ffmpeg()
    work = Path(cfg.work_dir); work.mkdir(parents=True, exist_ok=True)
    out = Path(cfg.out_dir); out.mkdir(parents=True, exist_ok=True)

    on_progress(8, "Transcribing audio")
    transcript = transcribe.transcribe(media_path, cfg)
    if not transcript["words"]:
        raise RuntimeError("No speech found in this file.")

    on_progress(32, "Finding the best moments")
    clips = score.score(transcript, cfg)
    if not clips:
        raise RuntimeError("The model returned no usable clips. Try a longer source video.")

    results = []
    span = 60.0 / len(clips)
    for i, clip in enumerate(clips):
        base = 38 + int(i * span)
        name = f"{i+1:02d}-{_slug(clip['title'], f'clip-{i+1}')}"
        on_progress(base, f"Cutting clip {i+1} of {len(clips)}")

        seg = ffmpeg_util.cut(media_path, clip["start"], clip["end"], str(work / f"{name}-seg.mp4"))

        on_progress(base + int(span * 0.4), f"Reframing clip {i+1}")
        vert = crop.reframe(seg, str(work / f"{name}-vert.mp4"), cfg)

        on_progress(base + int(span * 0.7), f"Captioning clip {i+1}")
        cw = _clip_words(transcript["words"], clip["start"], clip["end"])
        ass = captions.write_ass(cw, str(work / f"{name}.ass"), cfg)
        final = captions.burn(vert, ass, str(out / f"{name}.mp4"), cfg)

        results.append({
            "file": Path(final).name,
            "title": clip["title"],
            "reason": clip["reason"],
            "start": clip["start"],
            "end": clip["end"],
            "length": round(clip["end"] - clip["start"], 1),
        })

    on_progress(100, f"Done - {len(results)} clips ready")
    return results
