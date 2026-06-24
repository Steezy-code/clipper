# clipper

A local, **Ollama-powered** OpusClip alternative. Drop a long video → it transcribes,
picks the strongest moments, scores them for virality, tracks the speaker into vertical,
burns word-by-word karaoke captions with an auto hook headline, and hands you finished
shorts. Nothing is uploaded; everything runs on your machine.

```
Listen   →   Select   →   Reframe   →   Caption   →   Export
Whisper      Ollama       face track    karaoke       ffmpeg
```

## Start it (the two commands you'll use every time)

Open a **new** PowerShell window in this folder, then:

```powershell
# 1. make sure Ollama is running (only needed once per reboot)
ollama serve

# 2. start clipper
.\.venv\Scripts\python.exe app.py
```

Then open **<http://localhost:8765>** and drop a video. Finished clips land in the
`clips\` folder. Press `Ctrl+C` in the terminal to stop it.

> Tip: if you just installed ffmpeg, open a **fresh** terminal first so Windows picks it
> up on your PATH.

On macOS / Linux the run command is `./.venv/bin/python app.py`.

## Controls (set per video, right under the drop zone)

- **Aspect** — `9:16` (default), `1:1`, or `16:9`
- **Captions** — `Karaoke`, `Boxed` (bar behind text), or `Bold`
- **Length** — `Auto (15–60s)`, `Under 30s`, `30–60s`, or `60–90s`
- **Clips** — how many to cut (1–12)
- **Layout** — `Fill` (single speaker), `Split` (talking head on top, your gameplay/B-roll clip on the bottom — reveals a background picker), or `Stream (auto facecam)` (detects a Twitch-style webcam box and stacks facecam over gameplay automatically). Stream falls back to Fill if no facecam is found.
- **Trim silence** — on by default; collapses dead air between words so clips feel tightly edited

Each finished clip shows a virality score and an auto-generated hook headline.

## First-time setup (only once)

You need **Python 3.10+**, **ffmpeg**, and **Ollama** with a chat model pulled.

**Windows**
```powershell
./setup.ps1
```
**macOS / Linux**
```bash
chmod +x setup.sh && ./setup.sh
```

The script makes a virtualenv, installs the Python deps, checks for ffmpeg, and pulls the
Ollama model. The YuNet face-detection model downloads itself on first run. On an NVIDIA
GPU, Whisper runs on CUDA automatically (the required CUDA runtime is in `requirements.txt`).

## Tuning the important knobs

Most things are now in the UI. For the rest, set environment variables before launching
(or edit `clipper/config.py`):

| Variable | Default | What it does |
|---|---|---|
| `CLIPPER_MODEL` | `qwen3:8b` | Ollama model that picks clips. `qwen3:14b` = better taste, slower, more VRAM. |
| `WHISPER_MODEL` | `base.en` | `small.en` more accurate, `large-v3` best (slower). |
| `DETECT_EVERY` | `6` | Run face detection every N frames. Higher = faster, slightly less precise tracking. |
| `TRIM_SILENCE` | `1` | Remove dead air between words. Set `0` to keep pauses (e.g. for music). |
| `SILENCE_MAX` | `0.5` | Gaps longer than this (seconds) get collapsed when trimming. |
| `PUNCH_ZOOM` | `1` | Subtle zoom-in on emphasized words. Set `0` to disable motion. |
| `ZOOM_AMOUNT` | `0.08` | Max extra zoom at a punch (0.08 = 8%). |
| `SPLIT_RATIO` | `0.5` | Talking-head fraction of the frame in Split layout (top half). |
| `SMOOTH_ALPHA` | `0.12` | Camera glide. **Lower = smoother but laggier**, higher = snappier. |
| `ACCENT_HEX` | `#FF5C38` | Active-word caption color. |
| `USE_NVENC` | `1` | Set `0` to encode on CPU if you have no NVIDIA GPU. |

The defaults favor speed. For higher quality at the cost of time, set
`CLIPPER_MODEL=qwen3:14b` and `WHISPER_MODEL=small.en` (or `large-v3`). Transcription and
clip-scoring don't run at the same instant, so a 12 GB card handles `large-v3` + `qwen3:14b`
without fighting over VRAM.

## Honest limits

- **Face tracking** assumes one main speaker. Crowds or fast cuts confuse it — raise
  `SMOOTH_ALPHA` or fall back to center crop (see `docs/tuning.md`).
- **Captions** need a font installed; the default is Arial. Swap via `FONT_NAME`.
- Clip *taste* is only as good as the model. `qwen3:14b` is a noticeable step up over `8b`.
- Single-user/local by design — it doesn't namespace output per job, so run one video at a time.

See `docs/architecture.md` for how the pieces fit and where to extend.
