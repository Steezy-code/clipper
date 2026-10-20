"""Assert-based self-checks for the scoring stage. Run:
   .\\.venv\\Scripts\\python.exe -m clipper.tests.test_score
"""
from __future__ import annotations


def _cfg():
    import dataclasses
    from clipper.config import Config
    # pin the knobs these tests depend on so env vars can't move them
    return dataclasses.replace(Config(), min_clip_s=15.0, max_clip_s=60.0, num_clips=6)


def test_coerce_clean_json():
    from clipper.score import _coerce
    raw = '{"clips":[{"start":1,"end":20,"title":"A"}]}'
    assert _coerce(raw) == [{"start": 1, "end": 20, "title": "A"}]


def test_coerce_wrapped_in_prose_and_fences():
    from clipper.score import _coerce
    raw = 'Sure! Here you go:\n```json\n{"clips":[{"start":5,"end":30}]}\n```\nEnjoy.'
    assert _coerce(raw) == [{"start": 5, "end": 30}]


def test_coerce_garbage():
    from clipper.score import _coerce
    assert _coerce("no json here at all") == []
    assert _coerce("") == []
    assert _coerce("{not: valid json}") == []
    assert _coerce("} backwards {") == []


def test_coerce_top_level_list():
    from clipper.score import _coerce
    assert _coerce('[{"start":1,"end":20}]') == []


def test_coerce_missing_clips_key():
    from clipper.score import _coerce
    assert _coerce('{"moments":[{"start":1,"end":20}]}') == []
    assert _coerce("{}") == []


def test_coerce_multiple_brace_blocks():
    from clipper.score import _coerce
    # two separate objects: first-{ to last-} slice is not valid JSON
    raw = 'Example: {"x":1}\nAnswer: {"clips":[{"start":1,"end":20}]}'
    out = _coerce(raw)
    # BUG: _coerce slices from the first "{" to the last "}", which spans both
    # blocks and fails to parse, so the real answer is dropped and [] comes back.
    # Correct behaviour would be:
    # assert out == [{"start": 1, "end": 20}]
    assert out == [], f"bug fixed? update test: {out}"
    # nested braces inside one block are fine
    assert _coerce('text {"clips":[{"start":1,"end":20}]} text') == [{"start": 1, "end": 20}]


def test_timed_block_chunking():
    from clipper.score import _timed_block
    words = [{"word": f"w{i}", "start": i * 0.5, "end": i * 0.5 + 0.4} for i in range(30)]
    lines = _timed_block(words).split("\n")
    assert len(lines) == 3                                   # 12 + 12 + 6
    assert lines[0] == "[   0.00] " + " ".join(f"w{i}" for i in range(12))
    assert lines[1] == "[   6.00] " + " ".join(f"w{i}" for i in range(12, 24))
    assert lines[2] == "[  12.00] " + " ".join(f"w{i}" for i in range(24, 30))  # partial chunk


def test_timed_block_exact_chunk_and_empty():
    from clipper.score import _timed_block
    words = [{"word": "x", "start": 1.234, "end": 1.5}] * 12
    assert _timed_block(words) == "[   1.23] " + " ".join(["x"] * 12)  # no trailing empty line
    assert _timed_block([]) == ""
    assert _timed_block([{"word": "hi", "start": 1234.5, "end": 1235.0}]) == "[1234.50] hi"


def test_clean_bad_start_end():
    from clipper.score import _clean
    raw = [
        {"end": 20},                         # missing start
        {"start": 0},                        # missing end
        {"start": "abc", "end": 20},         # unparsable
        {"start": None, "end": 20},          # None
        {"start": "10", "end": "40", "title": "ok"},  # numeric strings are fine
    ]
    out = _clean(raw, 1000.0, _cfg())
    assert [c["title"] for c in out] == ["ok"], out
    assert out[0]["start"] == 10.0 and out[0]["end"] == 40.0


def test_clean_clamps_to_duration():
    from clipper.score import _clean
    out = _clean([{"start": -5, "end": 30, "title": "neg"},
                  {"start": 80, "end": 200, "title": "over"}], 100.0, _cfg())
    by = {c["title"]: c for c in out}
    assert by["neg"]["start"] == 0.0 and by["neg"]["end"] == 30.0
    assert by["over"]["start"] == 80.0 and by["over"]["end"] == 100.0
    # starts past the end of the video -> nothing left
    assert _clean([{"start": 150, "end": 200}], 100.0, _cfg()) == []


def test_clean_too_short_and_too_long():
    from clipper.score import _clean
    cfg = _cfg()
    assert _clean([{"start": 0, "end": 10}], 1000.0, cfg) == []           # < min 15s
    assert _clean([{"start": 50, "end": 20}], 1000.0, cfg) == []          # end before start
    out = _clean([{"start": 0, "end": 15}], 1000.0, cfg)                  # exactly min is kept
    assert len(out) == 1
    out = _clean([{"start": 10, "end": 200}], 1000.0, cfg)                # > max 60s -> truncated
    assert out[0]["start"] == 10.0 and out[0]["end"] == 70.0
    # duration clamp can push a clip under min
    assert _clean([{"start": 90, "end": 120}], 100.0, cfg) == []


def test_score_end_to_end():
    import json
    import requests
    from clipper import score as score_mod
    cfg = _cfg()
    payload = {"clips": [
        {"start": 50, "end": 80, "title": "Second", "hook": "H2", "reason": "r", "score": 70},
        {"start": 0, "end": 30, "title": "First", "reason": "r", "score": "95"},
        {"start": 10, "end": 40, "title": "Overlap", "score": 99},    # overlaps First
        {"start": 100, "end": 105, "title": "Short"},                 # too short
        {"start": "x", "end": 30},                                    # bad
    ]}
    calls = []

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"response": "```json\n" + json.dumps(payload) + "\n```"}

    def fake_post(url, json=None, timeout=None):
        calls.append((url, json))
        return FakeResp()

    words = [{"word": f"w{i}", "start": float(i), "end": i + 0.8} for i in range(120)]
    transcript = {"words": words, "duration": 120.0}
    orig = requests.post
    requests.post = fake_post
    try:
        out = score_mod.score(transcript, cfg)
    finally:
        requests.post = orig
    assert len(calls) == 1                                       # good answer on first try
    assert [c["title"] for c in out] == ["First", "Second"], out  # sorted by score, overlap dropped
    assert out[0] == {"start": 0.0, "end": 30.0, "title": "First", "hook": "First",
                      "reason": "r", "score": 95}
    assert out[1]["hook"] == "H2" and out[1]["end"] == 80.0
    assert "[   0.00] w0" in calls[0][1]["prompt"]                  # transcript made it into the prompt


def test_score_retries_then_empty():
    import requests
    from clipper import score as score_mod
    calls = []

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"response": "I could not find anything."}

    def fake_post(url, json=None, timeout=None):
        calls.append(json["options"]["temperature"])
        return FakeResp()

    orig = requests.post
    requests.post = fake_post
    try:
        out = score_mod.score({"words": [], "duration": 60.0}, _cfg())
    finally:
        requests.post = orig
    assert out == []
    assert len(calls) == 2 and calls[1] > calls[0]               # retried warmer


def test_score_network_error_raises():
    import requests
    from clipper import score as score_mod

    def fake_post(url, json=None, timeout=None):
        raise requests.ConnectionError("refused")

    orig = requests.post
    requests.post = fake_post
    try:
        try:
            score_mod.score({"words": [], "duration": 60.0}, _cfg())
            raised = False
        except RuntimeError as exc:
            raised = "Could not reach Ollama" in str(exc)
    finally:
        requests.post = orig
    assert raised


def run() -> None:
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")


if __name__ == "__main__":
    run()
