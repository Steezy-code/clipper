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
  transcribe.py         analyze - faster-whisper, word-level timestamps
  score.py              analyze - Ollama picks clips, returns validated JSON
  trim.py               render - silence trim inside each clip
  crop.py               render - YuNet face track + 2-pass EMA smoothing, 9:16; burns captions in the same encode
  layout.py             render - split / stream compositing (alternative to crop)
  captions.py           render - ASS karaoke generation (burned during reframe)
  broll.py              render - opt-in Pexels B-roll cutaways
  pipeline.py           analyze (transcribe+score) -> render_clip (trim -> reframe/layout -> captions)
  tests/test_quality.py quality checks
ARCHITECTURE.md         architecture notes
docs/tuning.md          tuning notes
landing/                static Netlify landing page
setup.ps1 / setup.sh    environment setup
```

## Pipeline contract

`pipeline.process(media_path, cfg, on_progress) -> list[dict]` — wraps `analyze` + `render_all`;
`render_clip` renders one clip (used by `/api/regenerate` in `app.py`).
Each result: `{file, title, hook, reason, score, start, end, length}`. Files written to `cfg.out_dir`.
`on_progress(percent:int, message:str)` drives the UI filmstrip (Listen/Select/Reframe/Caption/Export);
`stageFromMessage` in `static/index.html` maps keywords (transcrib / finding|moment / cut|refram / caption / done).

## Conventions

- Stages are independent and swappable — keep them that way. Each takes `cfg`.
- All settings live in `config.py`; read from env so nothing is hard-coded in logic.
- ffmpeg is the only non-Python dependency. Shell out through `ffmpeg_util` where possible.
- No telemetry. Network calls: Ollama at `OLLAMA_URL` (localhost by default), the one-time
  YuNet model download in `crop.py`, and the Pexels API only when B-roll is enabled
  (`BROLL=1` + `PEXELS_API_KEY`, `broll.py`).

## Common commands

```bash
./.venv/bin/python app.py                      # run the web UI (Windows: .\.venv\Scripts\python.exe app.py)
./.venv/bin/python -m clipper.tests.test_quality   # quality tests
./.venv/bin/python -c "from clipper import pipeline, Config; \
  print(pipeline.process('in.mp4', Config()))" # headless run
```

## Likely next extensions

- Split-screen reframe when two faces are detected (currently picks the largest).
- Swap scoring to stream tokens so the UI can show the model's picks live.
