"""Orchestrates the five stages and reports progress as it goes."""
from __future__ import annotations
import re
from pathlib import Path
from typing import Callable

from .config import Config
from . import ffmpeg_util, transcribe, score, crop, captions, trim, layout, broll

Progress = Callable[[int, str], None]


def _slug(text: str, fallback: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return s[:40] or fallback


def analyze(media_path: str, cfg: Config, on_progress: Progress = lambda p, m: None) -> tuple[dict, list]:
    """Stages 1-2: transcribe + score. Returns (transcript, clips). The slow, reusable work."""
    ffmpeg_util.ensure_ffmpeg()
    on_progress(8, "Transcribing audio")
    transcript = transcribe.transcribe(media_path, cfg)
    if not transcript["words"]:
        raise RuntimeError("No speech found in this file.")

    on_progress(32, "Finding the best moments")
    clips = score.score(transcript, cfg)
    if not clips:
        raise RuntimeError("The model returned no usable clips. Try a longer source video.")
    return transcript, clips


def clip_name(clip: dict, i: int) -> str:
    # ponytail: not job-namespaced (single-user/localhost tool); if concurrent jobs are ever
    # supported, prefix with the job id.
    return f"{i+1:02d}-{_slug(clip['title'], f'clip-{i+1}')}"


def render_clip(media_path: str, words: list[dict], clip: dict, name: str, cfg: Config) -> dict:
    """Stages 3-4 for ONE clip: cut (drop silence) -> reframe/compose -> burn captions.
    Reused by the full run and by single-clip regeneration."""
    work = Path(cfg.work_dir); work.mkdir(parents=True, exist_ok=True)
    out = Path(cfg.out_dir); out.mkdir(parents=True, exist_ok=True)

    abs_words = [w for w in words if w["end"] > clip["start"] and w["start"] < clip["end"]]
    spans = (trim.keep_spans(abs_words, clip["start"], clip["end"], cfg)
             if cfg.trim_silence else [(clip["start"], clip["end"])])
    segpath = str(work / f"{name}-seg.mp4")
    if len(spans) == 1:
        seg = ffmpeg_util.cut(media_path, spans[0][0], spans[0][1], segpath, codec=cfg.video_codec)
    else:
        rel = [(a - clip["start"], b - clip["start"]) for a, b in spans]
        seg = ffmpeg_util.cut_spans(media_path, clip["start"], clip["end"], rel,
                                    segpath, codec=cfg.video_codec)

    cw = trim.remap(abs_words, spans)
    ass = captions.write_ass(cw, str(work / f"{name}.ass"), cfg, hook=clip.get("hook", ""))
    zoom_at = captions.emphasis_times(cw, cfg) if cfg.punch_zoom else None

    use_split = (cfg.layout == "split" and cfg.background_path
                 and Path(cfg.background_path).exists())
    facecam = crop.detect_facecam(seg, cfg) if cfg.layout == "stream" else None
    # B-roll cutaways apply to the single-speaker (fill) layout only
    broll_items, credits = [], []
    if cfg.broll and broll.have_key(cfg) and not use_split and not facecam:
        broll_items, credits = broll.gather(cw, cfg, work / "broll")

    if use_split:
        top_h, bottom_h = layout.split_dims(cfg.target_w, cfg.target_h, cfg.split_ratio)
        head = crop.reframe(seg, str(work / f"{name}-head.mp4"), cfg,
                            ass_path=None, zoom_at=zoom_at, out_w=cfg.target_w, out_h=top_h)
        final = layout.compose_split(head, cfg.background_path, ass,
                                     str(out / f"{name}.mp4"), cfg, bottom_h)
    elif facecam:
        top_h, bottom_h = layout.split_dims(cfg.target_w, cfg.target_h, cfg.split_ratio)
        final = layout.compose_stream(seg, facecam, ass, str(out / f"{name}.mp4"),
                                      cfg, top_h, bottom_h)
    elif broll_items:
        # render captionless, overlay cutaways, then burn captions on top so they stay visible
        base = crop.reframe(seg, str(work / f"{name}-base.mp4"), cfg,
                            ass_path=None, zoom_at=zoom_at)
        final = broll.add_broll(base, ass, broll_items, str(out / f"{name}.mp4"), cfg)
        lines = [f"{c['term']}: {c['photographer']} - {c['url']}" for c in credits]
        Path(out / f"{name}.credits.txt").write_text(
            "Stock video via Pexels (https://pexels.com)\n" + "\n".join(lines) + "\n",
            encoding="utf-8")
    else:
        # reframe burns the captions in the same encode pass (no separate caption round trip)
        final = crop.reframe(seg, str(out / f"{name}.mp4"), cfg, ass_path=ass, zoom_at=zoom_at)

    return {
        "file": Path(final).name,
        "title": clip["title"],
        "hook": clip.get("hook", clip["title"]),
        "reason": clip["reason"],
        "score": clip.get("score", 50),
        "start": clip["start"],
        "end": clip["end"],
        "length": round(clip["end"] - clip["start"], 1),
    }


def render_all(media_path: str, transcript: dict, clips: list, cfg: Config,
               on_progress: Progress = lambda p, m: None,
               on_clip: Callable[[dict], None] = lambda r: None) -> list[dict]:
    """Stages 3-4 for every clip, with progress. on_clip fires as each clip finishes
    so the UI can show clips appearing one by one."""
    results = []
    span = 60.0 / len(clips)
    for i, clip in enumerate(clips):
        base = 38 + int(i * span)
        on_progress(base, f"Cutting clip {i+1} of {len(clips)}")
        on_progress(base + int(span * 0.5), f"Reframing clip {i+1}")
        res = render_clip(media_path, transcript["words"], clip, clip_name(clip, i), cfg)
        results.append(res)
        on_clip(res)
    on_progress(100, f"Done - {len(results)} clips ready")
    return results


def process(media_path: str, cfg: Config, on_progress: Progress = lambda p, m: None) -> list[dict]:
    transcript, clips = analyze(media_path, cfg, on_progress)
    return render_all(media_path, transcript, clips, cfg, on_progress)
