"""Orchestrates the five stages and reports progress as it goes."""
from __future__ import annotations
import re
from pathlib import Path
from typing import Callable

from .config import Config
from . import ffmpeg_util, transcribe, score, crop, captions, trim

Progress = Callable[[int, str], None]


def _slug(text: str, fallback: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return s[:40] or fallback


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
        # ponytail: not job-namespaced (single-user/localhost tool); if concurrent jobs are ever supported, prefix name with the job id.
        name = f"{i+1:02d}-{_slug(clip['title'], f'clip-{i+1}')}"
        on_progress(base, f"Cutting clip {i+1} of {len(clips)}")

        abs_words = [w for w in transcript["words"]
                     if w["end"] > clip["start"] and w["start"] < clip["end"]]
        spans = (trim.keep_spans(abs_words, clip["start"], clip["end"], cfg)
                 if cfg.trim_silence else [(clip["start"], clip["end"])])
        segpath = str(work / f"{name}-seg.mp4")
        if len(spans) == 1:
            seg = ffmpeg_util.cut(media_path, spans[0][0], spans[0][1], segpath, codec=cfg.video_codec)
        else:
            rel = [(a - clip["start"], b - clip["start"]) for a, b in spans]
            seg = ffmpeg_util.cut_spans(media_path, clip["start"], clip["end"], rel,
                                        segpath, codec=cfg.video_codec)

        on_progress(base + int(span * 0.4), f"Captioning clip {i+1}")
        cw = trim.remap(abs_words, spans)
        ass = captions.write_ass(cw, str(work / f"{name}.ass"), cfg, hook=clip.get("hook", ""))

        # reframe burns the captions in the same encode pass (no separate caption round trip)
        on_progress(base + int(span * 0.7), f"Reframing clip {i+1}")
        zoom_at = captions.emphasis_times(cw, cfg) if cfg.punch_zoom else None
        final = crop.reframe(seg, str(out / f"{name}.mp4"), cfg, ass_path=ass, zoom_at=zoom_at)

        results.append({
            "file": Path(final).name,
            "title": clip["title"],
            "hook": clip.get("hook", clip["title"]),
            "reason": clip["reason"],
            "score": clip.get("score", 50),
            "start": clip["start"],
            "end": clip["end"],
            "length": round(clip["end"] - clip["start"], 1),
        })

    on_progress(100, f"Done - {len(results)} clips ready")
    return results
