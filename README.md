# clipper

**Drop in a long video. Get back scored, captioned, vertical shorts — entirely on your own machine.**

No upload, no cloud API, no subscription. faster-whisper listens, a local Qwen3 model picks
the moments, OpenCV tracks the speaker, ffmpeg cuts and burns the captions. Everything that
makes an OpusClip-style tool useful, running on hardware you already own.

```
Listen   →   Select   →   Trim   →   Reframe / Layout   →   Caption   →   Export
Whisper      Qwen3         silence     face track            karaoke      ffmpeg
```

## Why I built it

Every "AI clipper" I found was a subscription wrapper around an API call. I wanted the same
outcome — transcript in, scored vertical shorts out — running fully local: my GPU, my
transcript, my choice of model, nothing shipped off to a server per clip. Building it also
meant getting hands-on with the parts that actually make these tools feel good or bad: face
tracking that doesn't jitter, captions that land on the beat, and a scoring pass that's
honest about what it can and can't judge.

## What it does

- **Transcribes** with word-level timestamps (faster-whisper, GPU-accelerated)
- **Picks the strongest moments** with a local LLM (Qwen3 via Ollama) and scores each one
  0–100 for short-form virality, with an auto-generated hook headline
- **Trims silence** between words so clips feel tightly edited, no manual scrubbing
- **Tracks the speaker** into 9:16 / 1:1 / 16:9 with a smoothed virtual camera (no jitter,
  no lag) and a subtle punch-in zoom on emphasized words
- **Three layouts** — single speaker (Fill), speaker over your own gameplay/B-roll (Split),
  or automatic Twitch-style facecam/gameplay separation (Stream)
- **Auto B-roll** — optional stock-footage cutaways from Pexels on keyword moments
- **Burns karaoke captions** in three style presets, with keyword emphasis and the hook
  headline baked in
- **Regenerates a single clip** with new settings without re-running the slow stages
- **Remembers your brand** — accent color, font, and default caption style saved once

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Transcription | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (ctranslate2) | Word-level timestamps, CUDA when available |
| Clip selection | [Ollama](https://ollama.com) + Qwen3 | Local, swappable, no per-clip API cost |
| Face tracking | OpenCV (YuNet) | Fast, no GPU required, bundled fallback (Haar cascade) |
| Video | ffmpeg | The only non-Python dependency; does all the muscle work |
| Backend | FastAPI | Small, typed, easy to read end to end |
| Frontend | Vanilla JS, no build step | One HTML file, nothing to compile |

See [ARCHITECTURE.md](ARCHITECTURE.md) for how the pipeline stages fit together and why.

## Quickstart

**You need:** Python 3.10+, ffmpeg on PATH, Ollama running with a model pulled. An NVIDIA
GPU is optional but makes transcription and encoding much faster.

```powershell
# one-time setup
./setup.ps1          # macOS/Linux: chmod +x setup.sh && ./setup.sh

# every time you run it
ollama serve                          # once per reboot
.\.venv\Scripts\python.exe app.py     # macOS/Linux: ./.venv/bin/python app.py
```

Open **http://localhost:8765**, drop a video. Finished clips land in `clips/`.

For **auto B-roll**, get a free key at [pexels.com/api](https://www.pexels.com/api/), copy
`.env.example` to `.env`, and paste it in — gitignored, loaded automatically:
```
PEXELS_API_KEY=your_key_here
```

## Controls

| Control | Options |
|---|---|
| Aspect | `9:16` (default), `1:1`, `16:9` |
| Captions | `Karaoke`, `Boxed`, `Bold` |
| Length | `Auto (15–60s)`, `Under 30s`, `30–60s`, `60–90s` |
| Layout | `Fill`, `Split` (+ your background clip), `Stream` (auto facecam) |
| Trim silence | On by default |
| B-roll | Off by default, needs `PEXELS_API_KEY` |
| Brand kit | Accent color, caption font, default style — saved once |

Every clip shows a virality score and hook headline; hit **↻** on any card to re-render just
that clip with new settings — it reuses the transcript, so it's fast.

## Tuning

Most of it lives in the UI. The rest is env vars (or edit `clipper/config.py`) — see the
full table in [ARCHITECTURE.md](ARCHITECTURE.md) and `docs/tuning.md` for troubleshooting
jittery tracking, weak clip picks, and slow transcription.

## Honest limits

- **Face tracking** assumes one main speaker; crowds or fast cuts confuse it.
- **Captions** need a font installed locally — default is Arial, swap via `FONT_NAME`.
- **Clip taste** is bounded by the model. `qwen3:14b` is a noticeable step up over the
  default `8b` if you have the VRAM to spare.
- **Single-user by design** — output isn't job-namespaced, so run one video at a time.
- **B-roll needs a free Pexels key**; without one the toggle is a no-op, not an error.

## License

[MIT](LICENSE)
