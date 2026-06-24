# Quality Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add virality scores, auto hook headlines, selectable caption styles with keyword emphasis, and per-video aspect ratios to the existing clipper pipeline.

**Architecture:** Additive changes to four existing stage modules plus the web layer. Each upload builds its own `Config` via `dataclasses.replace`; the scoring model returns `hook` + `score` alongside existing fields; captions gain style presets and heuristic keyword emphasis; aspect ratios flow through the unchanged `crop.py`.

**Tech Stack:** Python 3.14, FastAPI, faster-whisper, Ollama (qwen3), OpenCV, ffmpeg/libass (ASS subtitles), vanilla JS frontend.

## Global Constraints

- Windows; run Python via `.\.venv\Scripts\python.exe` from the project root `C:\Users\lwild\OneDrive\Desktop\Clipper`.
- No test framework. Tests are `assert`-based functions in `clipper/tests/test_quality.py`, run with `.\.venv\Scripts\python.exe -m clipper.tests.test_quality`. A new test "fails" by raising (AssertionError / AttributeError / ImportError) before its feature exists.
- Not a git repo. Either run `git init` once (Task 0) to enable the `git commit` steps, or treat each **Commit** step as a checkpoint and skip it.
- Keep stages independent and `cfg`-driven (existing convention). No new pip dependencies.
- Aspect map (verbatim): `9:16→1080×1920`, `1:1→1080×1080`, `16:9→1920×1080`.
- Caption styles (verbatim): `karaoke`, `boxed`, `bold`. Unknown → `karaoke`.
- `num_clips` clamps to 1–12. `score` clamps to 0–100, default 50. Missing `hook` → falls back to `title`.
- No emoji in captions (explicitly out of scope).

---

## Task 0: (Optional) Enable commits + test package

**Files:**
- Create: `clipper/tests/__init__.py` (empty)
- Create: `clipper/tests/test_quality.py` (runner skeleton)

- [ ] **Step 1: (optional) init git** so later commit steps work.

```bash
git init && git add -A && git commit -m "chore: baseline before quality layer"
```

- [ ] **Step 2: Create the test package**

`clipper/tests/__init__.py`: empty file.

`clipper/tests/test_quality.py`:
```python
"""Assert-based self-checks for the quality layer. Run:
   .\\.venv\\Scripts\\python.exe -m clipper.tests.test_quality
"""
from __future__ import annotations


def run() -> None:
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")


if __name__ == "__main__":
    run()
```

- [ ] **Step 3: Run it (empty suite passes)**

Run: `.\.venv\Scripts\python.exe -m clipper.tests.test_quality`
Expected: `0 passed`

- [ ] **Step 4: Commit**

```bash
git add clipper/tests/__init__.py clipper/tests/test_quality.py
git commit -m "test: add assert-based test runner"
```

---

## Task 1: Config fields + override validator

**Files:**
- Modify: `clipper/config.py`
- Test: `clipper/tests/test_quality.py`

**Interfaces:**
- Produces: `clipper.config.ASPECTS: dict[str, tuple[int,int]]`, `clipper.config.CAPTION_STYLES: tuple[str,...]`, `clipper.config.validate_overrides(form: dict) -> dict`, and a new `Config.caption_style: str` field.

- [ ] **Step 1: Write the failing test** — add to `clipper/tests/test_quality.py`:

```python
def test_validate_overrides():
    from clipper.config import validate_overrides
    o = validate_overrides({"aspect": "1:1", "caption_style": "bold", "num_clips": "99"})
    assert o == {"target_w": 1080, "target_h": 1080, "caption_style": "bold", "num_clips": 12}, o
    assert validate_overrides({"aspect": "bogus", "caption_style": "x", "num_clips": "abc"}) == {}
    assert validate_overrides({"num_clips": "0"})["num_clips"] == 1
    assert validate_overrides({"aspect": "16:9"}) == {"target_w": 1920, "target_h": 1080}


def test_config_has_caption_style():
    from clipper.config import Config
    assert Config().caption_style == "karaoke"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.\.venv\Scripts\python.exe -m clipper.tests.test_quality`
Expected: FAIL — `ImportError: cannot import name 'validate_overrides'`

- [ ] **Step 3: Implement** — in `clipper/config.py`, add the `caption_style` field to the dataclass (next to the other caption settings):

```python
    caption_style: str = os.environ.get("CAPTION_STYLE", "karaoke")
```

And add, after the `Config` class (module level, at end of file):

```python
ASPECTS: dict[str, tuple[int, int]] = {
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "16:9": (1920, 1080),
}
CAPTION_STYLES: tuple[str, ...] = ("karaoke", "boxed", "bold")


def validate_overrides(form: dict) -> dict:
    """Whitelist + clamp UI form fields into Config overrides. Bad values are dropped."""
    out: dict = {}
    if form.get("aspect") in ASPECTS:
        out["target_w"], out["target_h"] = ASPECTS[form["aspect"]]
    if form.get("caption_style") in CAPTION_STYLES:
        out["caption_style"] = form["caption_style"]
    n = form.get("num_clips")
    if n is not None:
        try:
            out["num_clips"] = max(1, min(12, int(n)))
        except (TypeError, ValueError):
            pass
    return out
```

- [ ] **Step 4: Run to verify it passes**

Run: `.\.venv\Scripts\python.exe -m clipper.tests.test_quality`
Expected: PASS (`ok  test_validate_overrides`, `ok  test_config_has_caption_style`)

- [ ] **Step 5: Commit**

```bash
git add clipper/config.py clipper/tests/test_quality.py
git commit -m "feat: config caption_style field + override validator"
```

---

## Task 2: Scoring returns hook + score, sorted by score

**Files:**
- Modify: `clipper/score.py`
- Test: `clipper/tests/test_quality.py`

**Interfaces:**
- Consumes: `Config` (with `num_clips`, `min_clip_s`, `max_clip_s`).
- Produces: `_clean(clips, duration, cfg)` now yields dicts with keys `start, end, title, hook, reason, score` (score int 0–100), sorted by `score` descending.

- [ ] **Step 1: Write the failing test** — add to `clipper/tests/test_quality.py`:

```python
def test_clean_score_hook_sort():
    from clipper.score import _clean
    from clipper.config import Config
    cfg = Config()
    raw = [
        {"start": 0, "end": 20, "title": "A", "reason": "r", "score": 40},
        {"start": 30, "end": 55, "title": "B", "hook": "Big hook here", "reason": "r", "score": 90},
        {"start": 60, "end": 80, "title": "C", "reason": "r"},          # no score, no hook
        {"start": 90, "end": 115, "title": "D", "reason": "r", "score": 250},  # out of range
    ]
    out = _clean(raw, 1000.0, cfg)
    assert out[0]["score"] == 100, out[0]            # 250 clamped, sorts first
    assert out[1]["score"] == 90 and out[1]["hook"] == "Big hook here"
    assert any(c["title"] == "C" and c["score"] == 50 and c["hook"] == "C" for c in out)
    for c in out:
        assert 0 <= c["score"] <= 100
        assert c["hook"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `.\.venv\Scripts\python.exe -m clipper.tests.test_quality`
Expected: FAIL — `KeyError: 'score'` or `KeyError: 'hook'`

- [ ] **Step 3a: Update the prompt** — in `clipper/score.py`, replace the JSON-shape line in `_SYSTEM` and add a scoring instruction:

```python
    "Favor a strong hook in the first seconds, a complete thought, and a clear payoff. "
    "Also write a punchy <=8 word on-screen headline ('hook') and a 'score' from 0-100 "
    "predicting its short-form virality. "
    "Return STRICT JSON only, no prose, in this exact shape:\n"
    '{{"clips":[{{"start":<seconds>,"end":<seconds>,"title":"<=6 words",'
    '"hook":"<=8 words","reason":"why it lands","score":<integer 0-100>}}]}}'
```

- [ ] **Step 3b: Update `_clean`** — replace the append + tail of `_clean`:

```python
        try:
            sc = int(float(c.get("score", 50)))
        except (TypeError, ValueError):
            sc = 50
        sc = max(0, min(100, sc))
        title = str(c.get("title", "Clip"))[:60]
        hook = str(c.get("hook") or title)[:80]
        out.append({"start": round(s, 2), "end": round(e, 2),
                    "title": title, "hook": hook,
                    "reason": str(c.get("reason", ""))[:200], "score": sc})
    out.sort(key=lambda c: c["start"])
    # drop overlaps, keep the earlier
    deduped: list[dict] = []
    for c in out:
        if deduped and c["start"] < deduped[-1]["end"]:
            continue
        deduped.append(c)
    deduped.sort(key=lambda c: c["score"], reverse=True)
    return deduped[: cfg.num_clips]
```

(Remove the old `out.append({...})`, old `out.sort`, and old `return deduped[: cfg.num_clips]` that this replaces.)

- [ ] **Step 4: Run to verify it passes**

Run: `.\.venv\Scripts\python.exe -m clipper.tests.test_quality`
Expected: PASS (`ok  test_clean_score_hook_sort`)

- [ ] **Step 5: Commit**

```bash
git add clipper/score.py clipper/tests/test_quality.py
git commit -m "feat: scoring returns hook + virality score, sorted by score"
```

---

## Task 3: Caption style presets, keyword emphasis, hook headline

**Files:**
- Modify: `clipper/captions.py`
- Test: `clipper/tests/test_quality.py`

**Interfaces:**
- Consumes: `Config.caption_style`, `Config.font_size`, `Config.accent_hex`, `Config.base_hex`, `Config.font_name`, `Config.target_w/h`.
- Produces: `clipper.captions.STYLES: dict[str, dict]`; `write_ass(words, path, cfg, hook="")` (new optional `hook` param) emitting `Style: Pop`, `Style: Hook`, the hook dialogue, and accent-emphasised keywords.

- [ ] **Step 1: Write the failing test** — add to `clipper/tests/test_quality.py`:

```python
def test_captions_styles_emphasis_hook():
    import dataclasses, tempfile, os
    from clipper.captions import write_ass, STYLES, _ass_color
    from clipper.config import Config
    base = Config()
    words = [{"word": "Productivity", "start": 0.0, "end": 0.4},
             {"word": "is", "start": 0.4, "end": 0.5},
             {"word": "everything", "start": 0.5, "end": 1.0}]
    accent = _ass_color(base.accent_hex)
    assert set(STYLES) == {"karaoke", "boxed", "bold"}
    for style in STYLES:
        cfg = dataclasses.replace(base, caption_style=style)
        p = os.path.join(tempfile.gettempdir(), f"t_{style}.ass")
        write_ass(words, p, cfg, hook="Stop wasting time")
        text = open(p, encoding="utf-8").read()
        assert "Style: Pop," in text
        assert "Style: Hook," in text
        assert "Stop wasting time" in text          # hook burned in
        assert accent in text                        # active word / keyword emphasis
```

- [ ] **Step 2: Run to verify it fails**

Run: `.\.venv\Scripts\python.exe -m clipper.tests.test_quality`
Expected: FAIL — `ImportError: cannot import name 'STYLES'`

- [ ] **Step 3a: Add presets + stopwords** — near the top of `clipper/captions.py` (after imports):

```python
STYLES: dict[str, dict] = {
    # size_mult scales cfg.font_size; border_style 1=outline, 3=opaque box.
    "karaoke": {"size_mult": 1.0, "border_style": 1, "outline": 6, "shadow": 3, "bold": 1},
    "boxed":   {"size_mult": 0.92, "border_style": 3, "outline": 4, "shadow": 0, "bold": 1},
    "bold":    {"size_mult": 1.18, "border_style": 1, "outline": 8, "shadow": 3, "bold": 1},
}

_STOP = {"the", "a", "an", "and", "or", "but", "to", "of", "in", "on", "for", "is",
         "are", "it", "this", "that", "you", "your", "i", "we", "they", "with", "as",
         "at", "be", "do", "does", "not", "so", "just", "like", "have", "has", "my"}


def _emphasis(line: list[dict]) -> set[int]:
    """Indices of up to 2 content words to keep tinted in the accent color."""
    idx = [i for i, w in enumerate(line)
           if len(w["word"].strip(".,!?'\"")) >= 4
           and w["word"].strip(".,!?'\"").lower() not in _STOP]
    return set(idx[:2])
```

- [ ] **Step 3b: Emphasise keywords in `_events`** — replace the token-building inner loop in `_events`:

```python
    for line in _lines(words, cfg):
        tokens = [_safe(w["word"]) for w in line]
        emph = _emphasis(line)
        for i, w in enumerate(line):
            start = w["start"]
            end = line[i + 1]["start"] if i + 1 < len(line) else w["end"]
            parts = []
            for j, tok in enumerate(tokens):
                if j == i:
                    parts.append(f"{{\\c{accent}\\fscx115\\fscy115\\b1}}{tok}{{\\r}}")
                elif j in emph:
                    parts.append(f"{{\\c{accent}}}{tok}{{\\r}}")
                else:
                    parts.append(tok)
            text = " ".join(parts)
            out.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Pop,,0,0,0,,{text}")
```

- [ ] **Step 3c: Style selection + hook in `write_ass`** — replace the body of `write_ass`:

```python
def write_ass(words: list[dict], path: str, cfg: Config, hook: str = "") -> str:
    base = _ass_color(cfg.base_hex)
    st = STYLES.get(cfg.caption_style, STYLES["karaoke"])
    size = int(cfg.font_size * st["size_mult"])
    hook_size = int(cfg.font_size * 0.7)
    pop = (f"Style: Pop,{cfg.font_name},{size},{base},&H00000000,&H64000000,"
           f"{st['bold']},{st['border_style']},{st['outline']},{st['shadow']},2,80,80,260")
    hook_style = (f"Style: Hook,{cfg.font_name},{hook_size},{base},&H00000000,&H64000000,"
                  f"1,1,5,2,8,60,60,120")
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {cfg.target_w}
PlayResY: {cfg.target_h}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV
{pop}
{hook_style}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = _events(words, cfg)
    if hook and words:
        end = words[-1]["end"]
        events = [f"Dialogue: 0,{_ts(0.0)},{_ts(end)},Hook,,0,0,0,,{_safe(hook)}"] + events
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return path
```

- [ ] **Step 4: Run to verify it passes**

Run: `.\.venv\Scripts\python.exe -m clipper.tests.test_quality`
Expected: PASS (`ok  test_captions_styles_emphasis_hook`)

- [ ] **Step 5: Commit**

```bash
git add clipper/captions.py clipper/tests/test_quality.py
git commit -m "feat: caption style presets, keyword emphasis, hook headline"
```

---

## Task 4: Thread hook + score through the pipeline

**Files:**
- Modify: `clipper/pipeline.py`

**Interfaces:**
- Consumes: `clip["hook"]`, `clip["score"]` from Task 2; `write_ass(..., hook=...)` from Task 3.
- Produces: result dicts with `hook` and `score` keys added.

- [ ] **Step 1: Update the caption call** — in `clipper/pipeline.py`, change the `write_ass` line:

```python
        ass = captions.write_ass(cw, str(work / f"{name}.ass"), cfg, hook=clip.get("hook", ""))
```

- [ ] **Step 2: Update the result dict** — change the `results.append({...})` block:

```python
        results.append({
            "file": Path(final).name,
            "title": clip["title"],
            "hook": clip.get("hook", clip["title"]),
            "reason": clip["reason"],
            "score": clip.get("score", 50),
            "start": clip["start"],
            "end": clip["end"],
            "length": round(clip["end"] - clip["start"], 1),
        })
```

- [ ] **Step 3: Verify end-to-end** (manual — needs Ollama + ffmpeg; reuse the smoke-test pattern). Generate a short narrated test clip, then:

Run:
```powershell
$base="C:\Users\lwild\OneDrive\Desktop\Clipper"; $py="$base\.venv\Scripts\python.exe"
$env:NUM_CLIPS="2"; $env:MIN_CLIP_S="8"
& $py -c "from clipper import pipeline, Config; import json; print(json.dumps(pipeline.process(r'PATH_TO_TEST.mp4', Config()), indent=2))"
```
Expected: each result dict contains non-empty `hook` and an integer `score` (0–100); clips are ordered highest `score` first.

- [ ] **Step 4: Commit**

```bash
git add clipper/pipeline.py
git commit -m "feat: pass hook to captions, add hook+score to results"
```

---

## Task 5: Per-job config from upload form

**Files:**
- Modify: `clipper/app.py`

**Interfaces:**
- Consumes: `validate_overrides` (Task 1).
- Produces: `/api/upload` accepts `aspect`, `caption_style`, `num_clips` form fields and runs each job with its own `Config`.

- [ ] **Step 1: Update imports + base config** — in `clipper/app.py`:

```python
from dataclasses import replace
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from clipper.config import Config, validate_overrides
from clipper import pipeline

base_cfg = Config()
```
(Replace the old `cfg = Config()` and the existing `from fastapi import ...` / config imports.)

- [ ] **Step 2: Thread cfg into the worker** — change `_run` to take a cfg:

```python
def _run(job_id: str, path: str, cfg: Config) -> None:
    def progress(percent: int, message: str) -> None:
        JOBS[job_id].update(percent=percent, message=message)
    try:
        clips = pipeline.process(path, cfg, progress)
        JOBS[job_id].update(status="done", percent=100, clips=clips)
    except Exception as exc:
        JOBS[job_id].update(status="error", error=str(exc))
```

- [ ] **Step 3: Accept form fields in `upload`** — change the handler signature and job start:

```python
@app.post("/api/upload")
async def upload(file: UploadFile = File(...),
                 aspect: str = Form("9:16"),
                 caption_style: str = Form("karaoke"),
                 num_clips: str = Form(None)) -> JSONResponse:
    if not file.filename:
        raise HTTPException(400, "No file provided.")
    job_id = uuid.uuid4().hex[:12]
    dest = UPLOADS / f"{job_id}-{Path(file.filename).name}"
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    job_cfg = replace(base_cfg, **validate_overrides(
        {"aspect": aspect, "caption_style": caption_style, "num_clips": num_clips}))
    JOBS[job_id] = {"status": "running", "percent": 0, "message": "Queued",
                    "clips": [], "error": None}
    threading.Thread(target=_run, args=(job_id, str(dest), job_cfg), daemon=True).start()
    return JSONResponse({"job": job_id})
```

- [ ] **Step 4: Fix the startup print** — change `cfg.model` to `base_cfg.model`:

```python
    print("clipper -> http://localhost:8765   (model: %s)" % base_cfg.model)
```

- [ ] **Step 5: Verify** — start the server (with refreshed PATH so ffmpeg is found) and post a job with fields:

Run:
```powershell
$machine=[Environment]::GetEnvironmentVariable("Path","Machine"); $u=[Environment]::GetEnvironmentVariable("Path","User"); $env:Path="$machine;$u"
$base="C:\Users\lwild\OneDrive\Desktop\Clipper"
& "$base\.venv\Scripts\python.exe" app.py
```
Then in another shell: `curl -s -F "file=@TEST.mp4" -F "aspect=1:1" -F "caption_style=bold" -F "num_clips=2" http://localhost:8765/api/upload`
Expected: `{"job":"..."}`, and polling `/api/status/<job>` ends with `done`; output clips are 1080×1080.

- [ ] **Step 6: Commit**

```bash
git add clipper/app.py
git commit -m "feat: per-job config from upload form fields"
```

---

## Task 6: UI controls panel + enriched result cards

**Files:**
- Modify: `static/index.html`

**Interfaces:**
- Consumes: `/api/upload` form fields (Task 5); result dicts with `hook` + `score` (Task 4).
- Produces: controls panel sends `aspect`/`caption_style`/`num_clips`; cards show score badge + hook.

- [ ] **Step 1: Add the controls markup** — insert directly after the `</label>` closing the dropzone, before `<section id="run" ...>`:

```html
  <div class="controls" id="controls">
    <div class="ctrl">
      <span class="clab">Aspect</span>
      <div class="seg" id="aspect" role="group" aria-label="Aspect ratio">
        <button type="button" data-v="9:16" class="on">9:16</button>
        <button type="button" data-v="1:1">1:1</button>
        <button type="button" data-v="16:9">16:9</button>
      </div>
    </div>
    <div class="ctrl">
      <span class="clab">Captions</span>
      <select id="capStyle">
        <option value="karaoke">Karaoke</option>
        <option value="boxed">Boxed</option>
        <option value="bold">Bold</option>
      </select>
    </div>
    <div class="ctrl">
      <span class="clab">Clips</span>
      <input type="number" id="numClips" min="1" max="12" value="6" />
    </div>
  </div>
```

- [ ] **Step 2: Add controls CSS** — add inside the `<style>` block (after the `.drop` rules):

```css
  .controls{display:flex;flex-wrap:wrap;gap:22px;margin:22px 2px 0;align-items:flex-end}
  .ctrl{display:flex;flex-direction:column;gap:8px}
  .clab{font-family:var(--display);text-transform:uppercase;letter-spacing:.16em;
    font-size:10px;color:var(--muted)}
  .seg{display:inline-flex;border:1px solid var(--line);border-radius:10px;overflow:hidden}
  .seg button{font-family:var(--display);font-size:13px;color:var(--muted);background:transparent;
    border:0;padding:9px 15px;cursor:pointer;transition:background .15s,color .15s}
  .seg button:hover{color:var(--text)}
  .seg button.on{background:var(--accent);color:var(--ink);font-weight:600}
  #capStyle,#numClips{font-family:var(--body);font-size:14px;color:var(--text);
    background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:9px 12px}
  #numClips{width:74px}
  #capStyle:focus,#numClips:focus{outline:2px solid var(--accent);outline-offset:1px}
  .badge-score{font-family:var(--display);font-weight:600;font-size:11px;border-radius:999px;
    padding:3px 9px;letter-spacing:.02em}
  .s-hi{background:rgba(61,220,151,.16);color:var(--done)}
  .s-mid{background:rgba(255,176,32,.16);color:#FFB020}
  .s-lo{background:var(--panel-2);color:var(--muted)}
  .card .head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin:0 0 6px}
```

- [ ] **Step 3: Track aspect + send fields** — in the `<script>`, after the `fileInput` listener, add aspect tracking:

```javascript
let aspect = "9:16";
document.querySelectorAll("#aspect button").forEach(b=>b.addEventListener("click",()=>{
  document.querySelectorAll("#aspect button").forEach(x=>x.classList.remove("on"));
  b.classList.add("on"); aspect = b.dataset.v;
}));
```

And in `start(file)`, replace the `FormData` block:

```javascript
  const fd = new FormData();
  fd.append("file", file);
  fd.append("aspect", aspect);
  fd.append("caption_style", document.getElementById("capStyle").value);
  fd.append("num_clips", document.getElementById("numClips").value);
```

- [ ] **Step 4: Show score + hook in `render`** — replace the `grid.innerHTML = clips.map(...)` block:

```javascript
  grid.innerHTML = clips.map((c,i)=>{
    const s = c.score ?? 50;
    const cls = s>=75 ? "s-hi" : s>=50 ? "s-mid" : "s-lo";
    return `
    <div class="card" style="animation-delay:${i*0.06}s">
      <video src="/clips/${encodeURIComponent(c.file)}" controls preload="metadata"></video>
      <div class="meta">
        <div class="head">
          <p class="t">${c.hook || c.title}</p>
          <span class="badge-score ${cls}">${s}</span>
        </div>
        <p class="r">${c.reason||""}</p>
        <div class="row">
          <span class="len">${c.length}s</span>
          <a class="dl" href="/clips/${encodeURIComponent(c.file)}" download>Download</a>
        </div>
      </div>
    </div>`;
  }).join("");
```

- [ ] **Step 5: Verify visually** — restart the server, refresh `http://localhost:8765`, confirm the controls row renders under the dropzone and a processed job shows score badges + hook headlines on the cards. Run a job with `aspect=1:1` and confirm the output card video is square.

- [ ] **Step 6: Commit**

```bash
git add static/index.html
git commit -m "feat: UI controls panel + score badge + hook on cards"
```

---

## Self-Review

**Spec coverage:**
- Per-job config → Task 1 (validator) + Task 5 (wiring). ✓
- Virality score → Task 2 (parse/clamp/sort) + Task 4 (result) + Task 6 (badge). ✓
- Hook headline → Task 2 (model) + Task 3 (burn) + Task 4 (result) + Task 6 (card). ✓
- Caption presets + keyword emphasis → Task 3. ✓
- Aspect ratios → Task 1 (map) + Task 5 (wiring) + Task 6 (selector); `crop.py` unchanged per spec. ✓
- UI controls panel + enriched cards → Task 6. ✓
- Self-check test → Tasks 0–3 build `test_quality.py`. ✓

**Placeholder scan:** none — every code step shows complete code; `PATH_TO_TEST.mp4`/`TEST.mp4` are explicit manual-input markers in verification steps, not code placeholders.

**Type consistency:** `validate_overrides(form: dict) -> dict` used identically in Tasks 1 and 5. `write_ass(words, path, cfg, hook="")` defined in Task 3, called with `hook=` in Task 4. Result keys `hook`/`score` produced in Tasks 2/4, consumed in Task 6. `STYLES` keys match the `CAPTION_STYLES` tuple. Consistent.
