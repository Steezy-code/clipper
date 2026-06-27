"""Web server: drag a video onto the page, watch it clip, download the results."""
from __future__ import annotations
import json
import shutil
import threading
import uuid
from dataclasses import replace
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse

# load a local .env (e.g. PEXELS_API_KEY) BEFORE importing config, which snapshots env vars
load_dotenv()

from clipper.config import Config, validate_overrides, validate_brand
from clipper import pipeline

BRAND_FILE = Path("brand.json")


def _load_brand() -> dict:
    try:
        return validate_brand(json.loads(BRAND_FILE.read_text(encoding="utf-8")))
    except Exception:
        return {}


base_cfg = replace(Config(), **_load_brand())   # apply saved brand defaults at startup
app = FastAPI(title="clipper")
STATIC = Path(__file__).parent / "static"
UPLOADS = Path("uploads"); UPLOADS.mkdir(exist_ok=True)

# in-memory, UI-facing job store: id -> {status, percent, message, clips, error}
JOBS: dict[str, dict] = {}
# internal per-job state for single-clip regeneration (not sent to the UI / not JSON)
JOB_STATE: dict[str, dict] = {}


def _run(job_id: str, path: str, cfg: Config) -> None:
    def progress(percent: int, message: str) -> None:
        JOBS[job_id].update(percent=percent, message=message)
    try:
        transcript, scored = pipeline.analyze(path, cfg, progress)
        # keep the slow-stage results so a single clip can be re-rendered later
        JOB_STATE[job_id] = {"transcript": transcript, "scored": scored, "media": path, "cfg": cfg}
        JOBS[job_id]["clips"] = []   # filled incrementally so the UI shows clips as they finish
        pipeline.render_all(path, transcript, scored, cfg, progress,
                            on_clip=lambda r: JOBS[job_id]["clips"].append(r))
        JOBS[job_id].update(status="done", percent=100)
    except Exception as exc:  # surface the real reason to the UI
        JOBS[job_id].update(status="error", error=str(exc))


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (STATIC / "index.html").read_text(encoding="utf-8")


@app.post("/api/upload")
async def upload(file: UploadFile = File(...),
                 background: UploadFile = File(None),
                 aspect: str = Form("9:16"),
                 caption_style: str = Form("karaoke"),
                 layout: str = Form("fill"),
                 length: str = Form("auto"),
                 trim: str = Form("1"),
                 broll: str = Form("0"),
                 num_clips: str = Form(None)) -> JSONResponse:
    if not file.filename:
        raise HTTPException(400, "No file provided.")
    job_id = uuid.uuid4().hex[:12]
    dest = UPLOADS / f"{job_id}-{Path(file.filename).name}"
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    bg_path = ""
    if background is not None and background.filename:
        bg_dest = UPLOADS / f"{job_id}-bg-{Path(background.filename).name}"
        with bg_dest.open("wb") as out:
            shutil.copyfileobj(background.file, out)
        bg_path = str(bg_dest)
    job_cfg = replace(base_cfg, background_path=bg_path, **validate_overrides(
        {"aspect": aspect, "caption_style": caption_style, "layout": layout,
         "length": length, "trim": trim, "broll": broll, "num_clips": num_clips}))
    JOBS[job_id] = {"status": "running", "percent": 0, "message": "Queued",
                    "clips": [], "error": None}
    threading.Thread(target=_run, args=(job_id, str(dest), job_cfg), daemon=True).start()
    return JSONResponse({"job": job_id})


@app.get("/api/status/{job_id}")
def status(job_id: str) -> JSONResponse:
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Unknown job.")
    return JSONResponse(job)


@app.post("/api/regenerate/{job_id}/{idx}")
def regenerate(job_id: str, idx: int,
               aspect: str = Form("9:16"),
               caption_style: str = Form("karaoke"),
               layout: str = Form("fill"),
               trim: str = Form("1")) -> JSONResponse:
    st, job = JOB_STATE.get(job_id), JOBS.get(job_id)
    if not st or not job:
        raise HTTPException(404, "Unknown job.")
    if idx < 0 or idx >= len(st["scored"]):
        raise HTTPException(404, "Unknown clip.")
    cfg = replace(st["cfg"], **validate_overrides(
        {"aspect": aspect, "caption_style": caption_style, "layout": layout, "trim": trim}))
    clip = st["scored"][idx]
    res = pipeline.render_clip(st["media"], st["transcript"]["words"], clip,
                              pipeline.clip_name(clip, idx), cfg)
    if idx < len(job.get("clips", [])):
        job["clips"][idx] = res
    return JSONResponse(res)


@app.get("/api/brand")
def get_brand() -> JSONResponse:
    return JSONResponse({"accent_hex": base_cfg.accent_hex,
                         "caption_style": base_cfg.caption_style,
                         "font_name": base_cfg.font_name})


@app.post("/api/brand")
def set_brand(accent_hex: str = Form(...), caption_style: str = Form(...),
              font_name: str = Form(...)) -> JSONResponse:
    global base_cfg
    v = validate_brand({"accent_hex": accent_hex, "caption_style": caption_style,
                        "font_name": font_name})
    BRAND_FILE.write_text(json.dumps(v), encoding="utf-8")
    base_cfg = replace(base_cfg, **v)
    return JSONResponse({"ok": True, **v})


@app.get("/clips/{name}")
def clip(name: str) -> FileResponse:
    path = Path(base_cfg.out_dir) / Path(name).name
    if not path.exists():
        raise HTTPException(404, "Clip not found.")
    return FileResponse(path, media_type="video/mp4")


if __name__ == "__main__":
    print("clipper -> http://localhost:8765   (model: %s)" % base_cfg.model)
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")
