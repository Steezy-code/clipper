"""Web server: drag a video onto the page, watch it clip, download the results."""
from __future__ import annotations
import shutil
import threading
import uuid
from pathlib import Path

import uvicorn
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse

from clipper.config import Config
from clipper import pipeline

cfg = Config()
app = FastAPI(title="clipper")
STATIC = Path(__file__).parent / "static"
UPLOADS = Path("uploads"); UPLOADS.mkdir(exist_ok=True)

# in-memory job store: id -> {status, percent, message, clips, error}
JOBS: dict[str, dict] = {}


def _run(job_id: str, path: str) -> None:
    def progress(percent: int, message: str) -> None:
        JOBS[job_id].update(percent=percent, message=message)
    try:
        clips = pipeline.process(path, cfg, progress)
        JOBS[job_id].update(status="done", percent=100, clips=clips)
    except Exception as exc:  # surface the real reason to the UI
        JOBS[job_id].update(status="error", error=str(exc))


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (STATIC / "index.html").read_text(encoding="utf-8")


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)) -> JSONResponse:
    if not file.filename:
        raise HTTPException(400, "No file provided.")
    job_id = uuid.uuid4().hex[:12]
    dest = UPLOADS / f"{job_id}-{Path(file.filename).name}"
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    JOBS[job_id] = {"status": "running", "percent": 0, "message": "Queued",
                    "clips": [], "error": None}
    threading.Thread(target=_run, args=(job_id, str(dest)), daemon=True).start()
    return JSONResponse({"job": job_id})


@app.get("/api/status/{job_id}")
def status(job_id: str) -> JSONResponse:
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Unknown job.")
    return JSONResponse(job)


@app.get("/clips/{name}")
def clip(name: str) -> FileResponse:
    path = Path(cfg.out_dir) / Path(name).name
    if not path.exists():
        raise HTTPException(404, "Clip not found.")
    return FileResponse(path, media_type="video/mp4")


if __name__ == "__main__":
    print("clipper -> http://localhost:8765   (model: %s)" % cfg.model)
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")
