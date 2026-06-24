"""Silence trimming driven by word timestamps - no audio analysis.

keep_spans() finds the speech regions of a clip, dropping gaps longer than
cfg.silence_max; remap() relocates word timestamps onto the concatenated
"tightened" timeline so burned captions still line up. Both are pure functions
of the Whisper word list, so the whole feature needs no extra decode pass.
"""
from __future__ import annotations
from .config import Config


def keep_spans(words: list[dict], start: float, end: float, cfg: Config) -> list[tuple[float, float]]:
    """Speech spans (absolute source time) within [start, end], gaps > silence_max removed.

    Empty/gapless input collapses to a single [start, end] span (a no-op cut).
    """
    inside = [w for w in words if w["end"] > start and w["start"] < end]
    if not inside:
        return [(start, end)]
    pad = cfg.silence_keep
    spans: list[list[float]] = []
    seg_start = max(start, inside[0]["start"] - pad)
    prev_end = inside[0]["end"]
    for w in inside[1:]:
        if w["start"] - prev_end > cfg.silence_max:
            spans.append([seg_start, min(end, prev_end + pad)])
            seg_start = max(start, w["start"] - pad)
        prev_end = w["end"]
    spans.append([seg_start, min(end, prev_end + pad)])
    # merge spans that touch/overlap after padding
    merged = [spans[0]]
    for a, b in spans[1:]:
        if a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [(a, b) for a, b in merged]


def remap(words: list[dict], spans: list[tuple[float, float]]) -> list[dict]:
    """Words relocated onto the concatenated spans timeline (relative to tightened start 0).

    Each word is placed by its start time into the span that contains it; words that
    fall entirely inside a removed gap are dropped. With a single full span this is
    just clip-relative timing (the no-trim path).
    """
    offsets, base = [], 0.0
    for a, b in spans:
        offsets.append(base)
        base += b - a
    out = []
    for w in words:
        for i, (a, b) in enumerate(spans):
            if a <= w["start"] < b:
                ns = w["start"] - a + offsets[i]
                ne = min(w["end"], b) - a + offsets[i]
                out.append({"word": w["word"], "start": ns, "end": max(ns, ne)})
                break
    return out
