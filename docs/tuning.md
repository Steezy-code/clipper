# Tuning

## Camera feels jittery / too floaty

`SMOOTH_ALPHA` controls the virtual camera. It's the weight given to each new face
detection in the moving average.

- **Jittery / snaps around** → lower it (`0.08`). Smoother, but it lags fast movement.
- **Laggy / drifts behind the speaker** → raise it (`0.2`–`0.3`). Snappier, more jitter.
- Default `0.12` suits a mostly-stationary talking head.

## Clip picks are weak

This is the model's judgment, not the plumbing.

- `CLIPPER_MODEL=qwen3:14b` — best instruction-following that still fits ~12 GB.
- `CLIPPER_MODEL=gemma3:12b` — briefer, less likely to overthink long transcripts.
- Widen the net with more clips and keep the best by eye.
- Tighten length to the range you want.

In the web UI, use the **Clips** (1–12) and **Length** controls; they override
`NUM_CLIPS` and `MIN_CLIP_S` / `MAX_CLIP_S` on every job. The env vars only set the
headless defaults.

## Transcription is slow or inaccurate

- Faster: `WHISPER_MODEL=base.en`.
- Better: `WHISPER_MODEL=large-v3` (more VRAM, slower, noticeably more accurate on
  accents and crosstalk).
- Force CPU if the GPU is busy: `WHISPER_DEVICE=cpu`.

## Captions

- Color: `ACCENT_HEX=#39E0A4` (any hex; default `#FF5C38`).
- Size/position: `FONT_SIZE`, and `MarginV` in the `Pop` style inside `captions.py`.
- Font: `FONT_NAME=Montserrat` — the font must be installed on the machine doing the
  ffmpeg burn.
- Words per line: `WORDS_PER_CAPTION=3` for a punchier, faster cadence.

In the web UI, set color and font in the **Brand kit** panel instead. A saved brand
(`brand.json`) overrides `ACCENT_HEX` and `FONT_NAME`.

## No NVIDIA GPU

`USE_NVENC=0` switches encoding to libx264 (CPU). Transcription falls back to CPU
automatically. It works, just slower.
