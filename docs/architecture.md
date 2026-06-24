# Architecture

Think of the whole thing as an editing-bay assembly line. Each station does one job and
hands its output to the next.

## The line

**1. Listen — `transcribe.py`**
faster-whisper turns audio into words *with timestamps*. Word-level timing is the
backbone: the scorer needs it to choose boundaries, and the captioner needs it to land
each highlight on the right frame. Device is auto-detected via ctranslate2 (CUDA if
present, else CPU at int8).

**2. Select — `score.py`**
The transcript is compressed into timestamped lines and handed to a local Ollama model
with `format: json`. The model returns clip boundaries + a title + a reason. We then
*validate*: clamp to the video length, enforce min/max duration, sort, and drop overlaps.
Never trust the raw JSON — `_clean()` is the guardrail.

**3. Reframe — `crop.py`** (the hard one)
YuNet detects the largest face every few frames. Raw detections are jittery, so we run a
**forward + backward exponential moving average** and average the two passes — this glides
the virtual camera and removes lag bias. We crop the largest 9:16 window that fits the
source and slide it along the tracked axis, then resize to the target resolution. Frames
are piped as raw BGR into ffmpeg so encoding (NVENC) and audio muxing happen in one pass.

**4. Caption — `captions.py`**
Words are grouped into short lines (breaking on pauses). For each word we emit one ASS
event where that word is recolored to the accent and scaled up — the "active word pops"
look — then reset. ffmpeg's `ass` filter burns them in.

**5. Export — `ffmpeg_util.py` + the above**
Everything is h264 / yuv420p / aac so the clips play anywhere. NVENC when available,
libx264 otherwise.

## Why this shape

- **Stateless stages.** Each function takes a path + `cfg` and returns a path. Easy to
  test, swap, or parallelize later.
- **The model is replaceable.** Scoring quality is bounded by the model; bump
  `CLIPPER_MODEL` to trade VRAM for taste without touching code.
- **One heavy dependency.** ffmpeg does the media muscle; Python does the orchestration.

## Where the cost is

Roughly: transcription scales with video length, reframing scales with clip length × count
(it decodes every frame), scoring is a single model call. On a 12 GB NVIDIA card a
10-minute source with 6 clips is minutes, not hours — reframing dominates.
