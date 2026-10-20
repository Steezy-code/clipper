"""Assert-based self-checks for ffmpeg_util. Run:
   .\\.venv\\Scripts\\python.exe -m clipper.tests.test_ffmpeg_util
"""
from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace


def _fake_ffprobe(streams, duration="12.5"):
    """Patch subprocess.run (as seen by ffmpeg_util) to return canned ffprobe JSON."""
    from clipper import ffmpeg_util
    out = json.dumps({"streams": streams, "format": {"duration": duration}})
    calls = []

    def fake_run(argv, **kw):
        calls.append(argv)
        return SimpleNamespace(stdout=out, returncode=0)

    ffmpeg_util.subprocess.run = fake_run
    return calls


def _probe(streams, **kw):
    from clipper import ffmpeg_util
    real = subprocess.run
    try:
        _fake_ffprobe(streams, **kw)
        return ffmpeg_util.probe("in.mp4")
    finally:
        ffmpeg_util.subprocess.run = real


def _video(rate=None, w=1920, h=1080):
    s = {"codec_type": "video", "width": w, "height": h}
    if rate is not None:
        s["r_frame_rate"] = rate
    return s


def _capture(fn, *args, **kw):
    """Run fn with subprocess.run captured; return the argv it was called with."""
    from clipper import ffmpeg_util
    calls = []
    real = subprocess.run
    ffmpeg_util.subprocess.run = lambda argv, **k: calls.append(argv)
    try:
        ret = fn(*args, **kw)
    finally:
        ffmpeg_util.subprocess.run = real
    assert len(calls) == 1, calls
    return ret, calls[0]


def test_even():
    from clipper.ffmpeg_util import even
    assert even(0) == 0
    assert even(4) == 4
    assert even(5) == 6
    assert even(1079) == 1080
    assert even(607.4) == 608      # rounds to 607, then bumped
    assert even(607.6) == 608      # rounds to 608
    assert even(2.5) == 2          # banker's rounding: round(2.5) == 2


def test_probe_ntsc_rate():
    p = _probe([_video("30000/1001")])
    assert abs(p["fps"] - 29.97) < 0.01, p
    assert p == {"width": 1920, "height": 1080, "fps": p["fps"], "duration": 12.5}


def test_probe_integer_rate():
    assert _probe([_video("25/1")])["fps"] == 25.0
    assert _probe([_video("25")])["fps"] == 25.0          # no slash -> den defaults to 1


def test_probe_missing_rate_defaults_30():
    assert _probe([_video()])["fps"] == 30.0


def test_probe_zero_rate():
    # BUG: r_frame_rate "0/0" (seen on some VFR/broken streams) raises ZeroDivisionError.
    # `den or 1` only guards an empty string; "0" is truthy, so float("0")/float("0") blows up
    # before the `fps > 0` fallback is reached. Documenting current behaviour, not fixing.
    try:
        _probe([_video("0/0")])
    except ZeroDivisionError:
        pass
    else:
        raise AssertionError("0/0 no longer raises - update this test (bug fixed?)")
    # "0/1" does reach the fallback.
    assert _probe([_video("0/1")])["fps"] == 30.0


def test_probe_audio_first_and_string_dims():
    p = _probe([{"codec_type": "audio"}, _video("24/1", w="1280", h="720")], duration="3.25")
    assert p == {"width": 1280, "height": 720, "fps": 24.0, "duration": 3.25}, p


def test_probe_argv():
    from clipper import ffmpeg_util
    real = subprocess.run
    try:
        calls = _fake_ffprobe([_video("30/1")])
        ffmpeg_util.probe("x y.mp4")
    finally:
        ffmpeg_util.subprocess.run = real
    assert calls[0][0] == "ffprobe" and calls[0][-1] == "x y.mp4", calls


def test_ensure_ffmpeg_missing():
    from clipper import ffmpeg_util
    real = ffmpeg_util.shutil.which
    try:
        ffmpeg_util.shutil.which = lambda name: None
        try:
            ffmpeg_util.ensure_ffmpeg()
        except RuntimeError as e:
            assert "ffmpeg/ffprobe not found" in str(e)
        else:
            raise AssertionError("expected RuntimeError")
        # Only ffprobe missing still raises.
        ffmpeg_util.shutil.which = lambda name: None if name == "ffprobe" else "/bin/ffmpeg"
        try:
            ffmpeg_util.ensure_ffmpeg()
        except RuntimeError:
            pass
        else:
            raise AssertionError("expected RuntimeError when ffprobe missing")
        ffmpeg_util.shutil.which = lambda name: "/bin/" + name
        ffmpeg_util.ensure_ffmpeg()
    finally:
        ffmpeg_util.shutil.which = real


def test_cut_argv():
    import tempfile
    from pathlib import Path
    from clipper.ffmpeg_util import cut
    with tempfile.TemporaryDirectory() as d:
        dst = str(Path(d) / "nested" / "out.mp4")
        ret, argv = _capture(cut, "in.mp4", 1.23456, 9.5, dst)
        assert ret == dst
        assert Path(dst).parent.is_dir()                   # parent dir created
        assert argv[:7] == ["ffmpeg", "-y", "-ss", "1.235", "-to", "9.500", "-i"], argv
        assert argv[7] == "in.mp4" and argv[-1] == dst
        assert argv[argv.index("-c:v") + 1] == "libx264"
        assert argv[argv.index("-preset") + 1] == "veryfast"
        assert argv[argv.index("-c:a") + 1] == "aac"
        assert "+faststart" in argv

        _, argv = _capture(cut, "in.mp4", 0, 1, dst, codec="h264_nvenc")
        assert argv[argv.index("-c:v") + 1] == "h264_nvenc"
        assert argv[argv.index("-preset") + 1] == "fast"


def test_cut_spans_argv():
    import tempfile
    from pathlib import Path
    from clipper.ffmpeg_util import cut_spans
    with tempfile.TemporaryDirectory() as d:
        dst = str(Path(d) / "a" / "b" / "out.mp4")
        spans = [(0.0, 1.5), (2.25, 4.0), (5.0, 6.1234)]
        ret, argv = _capture(cut_spans, "in.mp4", 10.0, 17.5, spans, dst)
        assert ret == dst and Path(dst).parent.is_dir()
        assert argv[:6] == ["ffmpeg", "-y", "-ss", "10.000", "-i", "in.mp4"], argv
        assert argv[argv.index("-t") + 1] == "7.500"
        assert argv[argv.index("-preset") + 1] == "veryfast"
        fc = argv[argv.index("-filter_complex") + 1].split(";")
        assert fc == [
            "[0:v]trim=0.000:1.500,setpts=PTS-STARTPTS[v0]",
            "[0:a]atrim=0.000:1.500,asetpts=PTS-STARTPTS[a0]",
            "[0:v]trim=2.250:4.000,setpts=PTS-STARTPTS[v1]",
            "[0:a]atrim=2.250:4.000,asetpts=PTS-STARTPTS[a1]",
            "[0:v]trim=5.000:6.123,setpts=PTS-STARTPTS[v2]",
            "[0:a]atrim=5.000:6.123,asetpts=PTS-STARTPTS[a2]",
            "[v0][a0][v1][a1][v2][a2]concat=n=3:v=1:a=1[v][a]",
        ], fc
        i = argv.index("-map")
        assert argv[i:i + 4] == ["-map", "[v]", "-map", "[a]"]

        _, argv = _capture(cut_spans, "in.mp4", 0, 2, [(0.0, 2.0)], dst, codec="hevc_nvenc")
        assert argv[argv.index("-preset") + 1] == "fast"
        assert argv[argv.index("-filter_complex") + 1].endswith("[v0][a0]concat=n=1:v=1:a=1[v][a]")


def test_real_ffmpeg_smoke():
    import shutil
    import tempfile
    from pathlib import Path
    from clipper.ffmpeg_util import probe, cut, cut_spans
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        print("  (skipped: ffmpeg not on PATH)")
        return
    with tempfile.TemporaryDirectory() as d:
        src = str(Path(d) / "src.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25:duration=2",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", src],
            capture_output=True, check=True,
        )
        p = probe(src)
        assert p["width"] == 320 and p["height"] == 240 and p["fps"] == 25.0, p
        assert 1.9 < p["duration"] < 2.2, p

        c = cut(src, 0.5, 1.5, str(Path(d) / "out" / "cut.mp4"))
        assert 0.9 < probe(c)["duration"] < 1.2, probe(c)

        s = cut_spans(src, 0.0, 2.0, [(0.0, 0.5), (1.0, 1.5)], str(Path(d) / "out" / "spans.mp4"))
        assert 0.9 < probe(s)["duration"] < 1.2, probe(s)


def run() -> None:
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")


if __name__ == "__main__":
    run()
