# CLAUDE.md

Project context for Claude Code when working in this repo.

## What this is

`clipper` — a local OpusClip alternative. Long video in, vertical captioned shorts out.
Fully local: faster-whisper for transcription, a local Ollama model for clip selection,
OpenCV (YuNet) for face-tracked reframing, ffmpeg for cutting and encoding.

## Layout

```
app.py                  FastAPI server + drag-drop UI, background job runner
static/index.html       Single-page UI (vanilla JS, no build step)
clipper/
  config.py             All tunables (env-var backed dataclass)
  ffmpeg_util.py        probe / cut / ensure_ffmpeg helpers
  transcribe.py         Stage 1 - faster-whisper, word-level timestamps
  score.py              Stage 2 - Ollama picks clips, returns validated JSON
  crop.py               Stage 3 - YuNet face track + 2-pass EMA smoothing, 9:16; burns captions in the same encode
  captions.py           Stage 4 - ASS karaoke generation (burned during reframe)
  pipeline.py           Orchestrates all stages, reports progress
docs/                   architecture + tuning notes
```

## Pipeline contract

`pipeline.process(media_path, cfg, on_progress) -> list[dict]`
Each result: `{file, title, reason, start, end, length}`. Files written to `cfg.out_dir`.
`on_progress(percent:int, message:str)` drives the UI filmstrip; the UI maps message
keywords (transcrib / finding / cut|refram / caption / done) to stages.

## Conventions

- Stages are independent and swappable — keep them that way. Each takes `cfg`.
- All settings live in `config.py`; read from env so nothing is hard-coded in logic.
- ffmpeg is the only non-Python dependency. Shell out through `ffmpeg_util` where possible.
- No telemetry, no network calls except the one-time YuNet model download in `crop.py`.

## Common commands

```bash
./.venv/bin/python app.py                      # run the web UI
./.venv/bin/python -c "from clipper import pipeline, Config; \
  print(pipeline.process('in.mp4', Config()))" # headless run
```

## Likely next extensions

- Split-screen reframe when two faces are detected (currently picks the largest).
- B-roll / zoom punches on emphasis words.
- A "regenerate this clip only" action in the UI.
- Swap scoring to stream tokens so the UI can show the model's picks live.
