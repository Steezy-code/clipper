"""Assert-based self-checks for the FastAPI server (app.py). Run:
   .\\.venv\\Scripts\\python.exe -m clipper.tests.test_app
Runs in a temp cwd (app.py writes uploads/ and brand.json relative to cwd); only the slow
pipeline stages are stubbed.
"""
from __future__ import annotations
import contextlib
import os
import tempfile
from dataclasses import replace
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="clipper-app-test-"))


@contextlib.contextmanager
def _app():
    """chdir into TMP, yield (app module, TestClient), restore cwd."""
    prev = os.getcwd()
    os.chdir(TMP)
    try:
        import app  # first import creates uploads/ and reads brand.json in TMP
        from fastapi.testclient import TestClient
        yield app, TestClient(app.app)
    finally:
        os.chdir(prev)


def _fake_job(app, job_id="job1", n=3):
    scored = [{"title": f"T{i}", "start": i * 10.0, "end": i * 10.0 + 5} for i in range(n)]
    app.JOB_STATE[job_id] = {"transcript": {"words": []}, "scored": scored,
                             "media": "in.mp4", "cfg": app.base_cfg}
    app.JOBS[job_id] = {"status": "done", "percent": 100, "message": "",
                        "clips": [{"file": f"old{i}"} for i in range(n)], "error": None}
    return scored


def test_status_unknown_job():
    with _app() as (app, c):
        r = c.get("/api/status/nope")
        assert r.status_code == 404, r.status_code
        app.JOBS["j"] = {"status": "running", "percent": 5, "message": "m", "clips": [], "error": None}
        assert c.get("/api/status/j").json()["percent"] == 5


def test_run_success_incremental():
    with _app() as (app, c):
        seen = []

        def analyze(path, cfg, progress):
            progress(10, "Transcribing audio")
            return {"words": []}, [{"title": "a"}, {"title": "b"}]

        def render_all(path, transcript, scored, cfg, progress, on_clip):
            for i, s in enumerate(scored):
                on_clip({"file": s["title"]})
                seen.append(len(app.JOBS["r"]["clips"]))  # visible as each clip finishes
            return []

        app.pipeline.analyze, app.pipeline.render_all = analyze, render_all
        app.JOBS["r"] = {"status": "running", "percent": 0, "message": "Queued", "clips": [], "error": None}
        app._run("r", "in.mp4", app.base_cfg)
        job = app.JOBS["r"]
        assert seen == [1, 2], seen
        assert job["status"] == "done" and job["percent"] == 100, job
        assert [x["file"] for x in job["clips"]] == ["a", "b"]
        assert job["message"] == "Transcribing audio"
        assert app.JOB_STATE["r"]["media"] == "in.mp4"


def test_run_error():
    with _app() as (app, c):
        def analyze(path, cfg, progress):
            raise RuntimeError("ffmpeg missing")
        app.pipeline.analyze = analyze
        app.JOBS["e"] = {"status": "running", "percent": 0, "message": "Queued", "clips": [], "error": None}
        app._run("e", "in.mp4", app.base_cfg)
        assert app.JOBS["e"]["status"] == "error"
        assert app.JOBS["e"]["error"] == "ffmpeg missing"
        assert c.get("/api/status/e").json()["status"] == "error"


def test_regenerate():
    with _app() as (app, c):
        calls = []
        app.pipeline.render_clip = lambda media, words, clip, name, cfg: (
            calls.append((clip, name, cfg)) or {"file": "new.mp4", "title": clip["title"]})
        scored = _fake_job(app, n=3)
        assert c.post("/api/regenerate/nope/0").status_code == 404
        assert c.post("/api/regenerate/job1/-1").status_code == 404
        assert c.post("/api/regenerate/job1/3").status_code == 404
        assert not calls
        r = c.post("/api/regenerate/job1/1",
                   data={"aspect": "1:1", "caption_style": "bold", "layout": "bogus", "trim": "0"})
        assert r.status_code == 200 and r.json()["file"] == "new.mp4", r.text
        clip, name, cfg = calls[0]
        assert clip is scored[1] and name == app.pipeline.clip_name(scored[1], 1)
        assert (cfg.target_w, cfg.target_h) == (1080, 1080)
        assert cfg.caption_style == "bold" and cfg.trim_silence is False
        assert cfg.layout == app.base_cfg.layout        # invalid layout dropped
        clips = app.JOBS["job1"]["clips"]
        assert clips[1]["file"] == "new.mp4" and clips[0]["file"] == "old0" and clips[2]["file"] == "old2"


def test_brand_roundtrip():
    with _app() as (app, c):
        r = c.post("/api/brand", data={"accent_hex": "#aabbcc", "caption_style": "boxed",
                                       "font_name": "  Impact  "})
        assert r.status_code == 200 and r.json()["accent_hex"] == "#AABBCC", r.text
        assert app._load_brand() == {"accent_hex": "#AABBCC", "caption_style": "boxed",
                                     "font_name": "Impact"}
        assert (TMP / "brand.json").exists()
        g = c.get("/api/brand").json()
        assert g == {"accent_hex": "#AABBCC", "caption_style": "boxed", "font_name": "Impact"}, g
        # invalid values are dropped; in-memory brand keeps the previous good values
        r = c.post("/api/brand", data={"accent_hex": "red", "caption_style": "nope",
                                       "font_name": "x" * 100})
        assert r.status_code == 200
        g = c.get("/api/brand").json()
        assert g["accent_hex"] == "#AABBCC" and g["caption_style"] == "boxed"
        assert g["font_name"] == "x" * 64             # truncated
        # BUG: set_brand writes only the validated subset to brand.json, so a partly invalid
        # POST erases previously saved fields on disk (here accent/style) while base_cfg still
        # holds them -> after a restart the brand silently reverts.
        assert app._load_brand() == {"font_name": "x" * 64}
        assert c.post("/api/brand", data={"accent_hex": "#000000"}).status_code == 422  # missing fields


def test_load_brand_missing_or_corrupt():
    with _app() as (app, c):
        f = TMP / "brand.json"
        f.unlink(missing_ok=True)
        assert app._load_brand() == {}
        f.write_text("{not json", encoding="utf-8")
        assert app._load_brand() == {}
        f.write_text("[1, 2]", encoding="utf-8")       # valid JSON, wrong shape
        assert app._load_brand() == {}
        f.unlink()


def test_clips_serving_and_traversal():
    from fastapi import HTTPException
    with _app() as (app, c):
        out = TMP / "out"; out.mkdir(exist_ok=True)
        (out / "01-ok.mp4").write_bytes(b"clipdata")
        (TMP / "secret.mp4").write_bytes(b"secret")   # sibling of out_dir: must be unreachable
        app.base_cfg = replace(app.base_cfg, out_dir=str(out))
        r = c.get("/clips/01-ok.mp4")
        assert r.status_code == 200 and r.content == b"clipdata"
        assert c.get("/clips/missing.mp4").status_code == 404
        for url in ("/clips/..%2Fsecret.mp4", "/clips/%2E%2E%2Fsecret.mp4",
                    "/clips/..%5Csecret.mp4", "/clips/../secret.mp4", "/clips/..%2F..%2Fapp.py"):
            r = c.get(url)
            assert r.status_code == 404 and b"secret" not in r.content, (url, r.status_code)
        for name in ("../secret.mp4", "..\\secret.mp4", str(TMP / "secret.mp4")):
            try:
                app.clip(name)
                assert False, f"escaped out_dir: {name}"
            except HTTPException as e:
                assert e.status_code == 404


def run() -> None:
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")


if __name__ == "__main__":
    run()
