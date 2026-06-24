# clipper

A local, **Ollama-powered** OpusClip alternative. Drop a long video → it transcribes,
picks the strongest moments, tracks the speaker into vertical 9:16, burns word-by-word
karaoke captions, and hands you finished shorts. Nothing is uploaded; everything runs on
your machine.

```
Listen   →   Select   →   Reframe   →   Caption   →   Export
Whisper      Ollama       face track    karaoke       ffmpeg
```

## What you need

- **Python 3.10+**
- **ffmpeg** on your PATH
- **Ollama** running locally with one chat model pulled (default `qwen3:8b`)
- An NVIDIA GPU is optional but makes transcription + encoding much faster

## Setup (one command)

**Windows**
```powershell
./setup.ps1
```

**macOS / Linux**
```bash
chmod +x setup.sh && ./setup.sh
```

The script makes a virtualenv, installs the Python deps, checks for ffmpeg, and pulls the
Ollama model. The YuNet face-detection model downloads itself on first run.

## Run

```bash
# Windows
.\.venv\Scripts\python.exe app.py
# macOS / Linux
./.venv/bin/python app.py
```

Open <http://localhost:8765> and drop a video. Finished clips land in `clips/`.

## Tuning the important knobs

Set these as environment variables before launching (or edit `clipper/config.py`):

| Variable | Default | What it does |
|---|---|---|
| `CLIPPER_MODEL` | `qwen3:8b` | Ollama model that picks clips. `qwen3:14b` = better taste, more VRAM. |
| `WHISPER_MODEL` | `small.en` | `base.en` faster, `large-v3` best quality. |
| `NUM_CLIPS` | `6` | How many clips to cut. |
| `SMOOTH_ALPHA` | `0.12` | Camera glide. **Lower = smoother but laggier**, higher = snappier. |
| `ACCENT_HEX` | `#FF5C38` | Active-word caption color. |
| `USE_NVENC` | `1` | Set `0` to encode on CPU if you have no NVIDIA GPU. |

Memory tip: transcription and clip-scoring don't run at the same instant, so a 12 GB card
handles `large-v3` for Whisper and `qwen3:8b`/`14b` for scoring without fighting over VRAM.

## Honest limits

- **Face tracking** assumes one main speaker. Crowds or fast cuts confuse it — raise
  `SMOOTH_ALPHA` or fall back to center crop (see `docs/tuning.md`).
- **Captions** need a font installed; the default is Arial. Swap via `FONT_NAME`.
- Clip *taste* is only as good as the model. `qwen3:14b` is a noticeable step up.

See `docs/architecture.md` for how the pieces fit and where to extend.
