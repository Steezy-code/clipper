# Quality Layer — Design Spec

**Date:** 2026-06-23
**Project:** A of 3 (Quality Layer → Layout System → Auto B-roll)
**Status:** Approved design, pre-implementation

## Goal

Close the most visible OpusClip-parity gap without rewriting the working pipeline.
Add, per clip: a virality score, an auto-generated hook headline burned onto the
video, selectable caption styles with keyword color-emphasis, and per-video aspect
ratio — all surfaced through a compact controls panel in the UI.

All changes are additive to the existing five-stage pipeline
(`transcribe → score → crop → caption → export`). The `transcribe` and `crop`
stages are untouched.

## Scope

In scope:
- Per-job configuration (each upload gets its own `Config`)
- Virality score (0–100) per clip, returned by the scoring model
- Auto hook headline per clip, burned as a persistent top title
- Three caption style presets + heuristic keyword color-emphasis
- Aspect ratio selection: 9:16, 1:1, 16:9
- UI controls panel + enriched result cards
- One self-check test

Out of scope (later projects):
- Layout system / Twitch facecam separation / gameplay split (Project B)
- Auto B-roll from stock APIs (Project C)
- Emoji in captions (explicitly declined)
- Brand-kit presets, chapters

## Architecture

The pipeline contract is unchanged: `pipeline.process(media_path, cfg, on_progress)`.
Every feature is delivered by extending an existing stage or its `cfg`.

### 1. Per-job config — `app.py`, `config.py`

Today `app.py` holds one module-level `cfg`. Change: `/api/upload` reads optional
form fields, validates them, and builds a job-specific config with
`dataclasses.replace(base_cfg, **overrides)`.

- `Config` stays a frozen-by-convention dataclass; no structural change beyond new fields.
- A single helper validates + clamps the incoming overrides (whitelist of keys).
  Invalid values fall back to the base default silently (no 400 for a bad dropdown).

Validated override fields:
| Field | Allowed | Default |
|---|---|---|
| `aspect` | `9:16`, `1:1`, `16:9` | `9:16` |
| `caption_style` | `karaoke`, `boxed`, `bold` | `karaoke` |
| `num_clips` | int 1–12 | `6` |

`aspect` resolves to `(target_w, target_h)`:
`9:16→1080×1920`, `1:1→1080×1080`, `16:9→1920×1080`.

New `Config` fields: `caption_style: str = "karaoke"`, plus an `aspect` string that
sets `target_w`/`target_h` (kept as the source of truth so `crop.py` is unchanged).

### 2. Virality score — `score.py`

Extend the system prompt's required JSON shape to:
```json
{"clips":[{"start":<s>,"end":<s>,"title":"<=6 words",
           "hook":"<=8 words punchy headline","reason":"why it lands",
           "score":<0-100>}]}
```
- `_clean` clamps `score` to 0–100; missing/non-numeric → `50`.
- After cleaning, sort clips by `score` descending (was: by start time). Overlap
  dedup still runs first on time order, then final sort is by score.
- `score` is added to each result dict from `pipeline.process`.

### 3. Auto hook headline — `score.py` + `captions.py`

- `score.py` returns `hook` per clip (≤8 words). `_clean` truncates and, if empty,
  falls back to `title`.
- `captions.py` gains a new ASS style `Hook` (top-aligned, alignment 8) and writes a
  single `Dialogue` event spanning the whole clip with the hook text.
- `pipeline.process` passes `clip["hook"]` into caption writing and includes `hook`
  in the result dict.

### 4. Caption styles + keyword emphasis — `captions.py`

**Presets** — a `STYLES: dict[str, dict]` maps a style name to ASS style parameters
(font size, outline, box/border style, alignment, margins). `write_ass` picks the
preset from `cfg.caption_style`; unknown names fall back to `karaoke`.
- `karaoke`: current look — white words, active word pops accent, bottom.
- `boxed`: `BorderStyle=3` opaque box behind text for readability over busy footage.
- `bold`: larger font, heavier weight, thicker outline.

**Keyword emphasis** — within `_events`, for each caption line pick 1–2 "content"
words to render in the accent color even when not the active word. Heuristic:
word length ≥ 4 and not in a small built-in stopword set; cap at 2 per line. The
active word still renders brightest (current accent + scale-up). No LLM call.

### 5. Aspect ratios — `crop.py` (no change)

`_crop_plan` already computes the largest target-ratio window for any
`target_w/target_h`, so 1:1 and 16:9 work by config alone.

### 6. UI — `static/index.html`

- A controls row near the dropzone (matching the polished dark/accent theme):
  - Aspect ratio: segmented control (9:16 / 1:1 / 16:9)
  - Caption style: dropdown (Karaoke / Boxed / Bold)
  - Clips: number input or stepper (1–12)
- `start()` appends these as form fields to the existing `FormData`.
- Result cards: add a score badge (green ≥75 / amber 50–74 / muted <50) and show the
  `hook` as the bold headline; existing `title` becomes the small secondary label.
- Card `<video>` keeps `aspect-ratio` driven by the chosen output ratio (default 9/16);
  for non-9:16 outputs the card media box adapts.

## Data flow

```
UI form (aspect, caption_style, num_clips)
  → POST /api/upload
  → validate+clamp → dataclasses.replace(base_cfg, overrides) → job cfg
  → pipeline.process(path, job_cfg, progress)
      score.py  → clips[{start,end,title,hook,reason,score}] (sorted by score desc)
      crop.py   → reframe to cfg.target_w×target_h
      captions  → STYLES[cfg.caption_style] + keyword emphasis + Hook headline
  → result[{file,title,hook,reason,score,start,end,length}]
  → UI cards (score badge + hook)
```

## Error handling

- Bad/missing form fields → clamped or defaulted, never a hard error.
- LLM omits `score` → 50; omits `hook` → falls back to `title`.
- Unknown `caption_style` → `karaoke`.
- Existing scoring retry (2 attempts, temperature bump) and Ollama-unreachable error
  are unchanged.

## Testing

`clipper/tests/test_quality.py` (no framework, `assert`-based, runnable as
`python -m clipper.tests.test_quality`):
- ASS output for a sample line contains the accent override for the active word and
  for at least one emphasized keyword.
- A `Hook` dialogue event is present when a hook is supplied.
- Each of the three presets produces a valid `[V4+ Styles]` block.
- Override validation clamps `num_clips`, rejects unknown `aspect`/`caption_style`.

## Files touched

- `clipper/config.py` — new fields, aspect→dimensions mapping, override validator
- `clipper/score.py` — schema (`hook`, `score`), clamp, sort-by-score
- `clipper/captions.py` — style presets, keyword emphasis, hook headline
- `clipper/app.py` — per-job config from validated form fields
- `clipper/pipeline.py` — pass `hook` into caption writing; add `hook` + `score` to
  each result dict (small change, no structural rework)
- `static/index.html` — controls panel + enriched cards
- `clipper/tests/test_quality.py` — new self-check

Untouched: `transcribe.py`, `crop.py`, `ffmpeg_util.py`.
