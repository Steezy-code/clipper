# FINDINGS — clipper audit (Phase 1)

Audit for turning `clipper` into a premium, public, portfolio-grade project.
**No code was changed to produce this.** The AI pipeline is treated as a protected engine.

## 1. What it is today

A local-first short-form video tool: long video in → vertical captioned shorts out.
~2,050 LOC across Python + one HTML page. FastAPI backend, vanilla-JS single-page frontend,
no build step.

### Architecture map

```
app.py                     FastAPI server, in-memory job store, background job runner
static/index.html          Single-page UI (vanilla JS, no framework/build)
clipper/
  config.py                Env-backed dataclass; per-job overrides; brand-kit + validators
  transcribe.py   [ENGINE] Stage 1 — faster-whisper, word-level timestamps (CUDA/CPU auto)
  score.py        [ENGINE] Stage 2 — Ollama/Qwen3 picks clips; returns validated JSON
  crop.py         [ENGINE] Stage 3 — YuNet face track + 2-pass EMA smoothing → 9:16
  captions.py     [ENGINE] Stage 4 — ASS karaoke generation (burned during reframe)
  trim.py                  Silence trimming from word timestamps
  layout.py                Split / stream (facecam) compositing
  broll.py                 Pexels stock-video cutaways (opt-in, needs key)
  ffmpeg_util.py           cut / cut_spans / probe / ensure_ffmpeg
  pipeline.py              Orchestrates analyze() + render_clip()/render_all()
  tests/test_quality.py    17 assert-based checks (no framework)
docs/                      architecture.md, tuning.md, superpowers/ (internal planning)
```

### Backend routes
- `GET /` — serves the SPA
- `POST /api/upload` — accepts video (+ optional background), per-job controls → starts job
- `GET /api/status/{job}` — poll status/percent/message/clips
- `POST /api/regenerate/{job}/{idx}` — re-render one clip with new settings
- `GET|POST /api/brand` — read/save brand kit
- `GET /clips/{name}` — serve a finished clip

### External deps
faster-whisper (ctranslate2), Ollama + Qwen3 (`qwen3:8b` default), OpenCV (YuNet),
ffmpeg/libass, FastAPI/uvicorn, python-dotenv. GPU (NVENC/CUDA) optional but recommended.

## 2. Already presentable vs. rough

**Presentable**
- Clean, modular, stateless-stage architecture — genuinely senior-signal code.
- Solid README with quickstart, controls, tuning table, honest limits.
- `docs/architecture.md` is well-written (but now **stale** — predates hook/score, trim,
  zoom, layouts, B-roll).
- 17 passing tests; strong `.gitignore`; env-var config; `.env.example`.
- The app UI is already a cut above default (dark theme, display font, filmstrip progress,
  score badges, hook headlines).

**Rough / unfinished / local-only**
- **No LICENSE.**
- **No demo assets** — zero screenshots or demo GIF. This is the single biggest gap for a
  resume-grade repo.
- **No landing page** — nothing clickable to link publicly.
- `docs/superpowers/` contains internal AI-workflow planning docs (plan + spec) with personal
  paths — process cruft, not portfolio material.
- `docs/architecture.md` is stale vs. the current feature set.
- The app UI, while good, does **not** yet match the target house style (dark "asphalt command
  rail" + light "plan-sheet" workspace; tabular-mono numerals; one signature element).

## 3. Presentation gaps for resume-grade

| Area | Status | Gap |
|---|---|---|
| README | Good, functional | Needs premium hook, demo GIF at top, architecture diagram, "why I built it" |
| Demo assets | Missing | Need a clean GIF/short of a real clip being produced |
| Landing page | Missing | The clickable resume artifact (static, Netlify) |
| LICENSE | Missing | Add MIT (or chosen) |
| ARCHITECTURE.md | Exists but stale | Refresh to current pipeline; promote as senior-signal doc |
| Repo hygiene | Strong | Scrub personal paths; drop internal planning docs |
| App UI polish | Good, off-style | Reskin to house style, view-layer only |

## 4. Sensitive-content scan

Scanned all tracked files + git history.

| Item | Result |
|---|---|
| `.env` / real API key in commits or history | **None** — `.env` never committed; no key blob in history |
| Personal Windows home-directory path | **Found** in `docs/superpowers/plans/2026-06-23-quality-layer.md` and `.../specs/2026-06-23-quality-layer-design.md` — must scrub or remove |
| Email / personal identifiers in tracked files | None found |
| "Friend's channel" / Twitch/YouTube handles | **None found** in repo (nothing to scrub here) |
| Secrets in README | Only the `PEXELS_API_KEY=your_key_here` **placeholder** — safe |
| `.gitignore` coverage | Strong: `.venv/`, `__pycache__/`, `uploads//work//clips/`, `clipper/models/`, `brand.json`, `.env` |
| Git author | `clipper <clipper@local>` — neutral, not personal |
| Remote | `github.com/Steezy-code/clipper` (your public handle — intended) |

**Verdict:** the repo is *nearly* public-safe. Only action required before going public:
scrub/remove the two `docs/superpowers/` files that embed the personal path.

## 5. Deploy constraints

- The processing backend is **GPU-bound and local** (CUDA whisper, NVENC, Ollama). A live
  public processing instance is **out of scope** — cost, GPU, and abuse surface make it
  impractical, and the brief explicitly rules it out.
- **Recommended clickable artifact:** a **static landing page on Netlify** (showcases, does
  not process — no backend calls) + a **premium README with a demo GIF**. The landing page
  is the resume link; the README + GIF carry the "it really works" proof.
- Landing page lives in `landing/` (self-contained static site), deployed to Netlify via
  drag-drop or Git integration.

## 6. Proposed signature element (one, not three)

**The virality-score gauge.** clipper already computes a 0–100 virality score per clip — a
score-meter is *native to the domain*, not decoration. A single semicircular gauge with a
sweeping needle and a large tabular-mono numeral becomes:
- the **hero visual** on the landing page (animated on load), and
- the **score element** in the app's results view (one per clip card).

This satisfies "one bold signature element" and ties the brand to the product's actual output.
Rejected alternatives (waveform, equalizer) are less tied to what clipper uniquely produces.

→ Proceeding directly to `PLAN.md`.
