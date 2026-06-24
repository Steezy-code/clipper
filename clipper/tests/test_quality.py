"""Assert-based self-checks for the quality layer. Run:
   .\\.venv\\Scripts\\python.exe -m clipper.tests.test_quality
"""
from __future__ import annotations


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


def test_validate_overrides_length():
    from clipper.config import validate_overrides
    assert validate_overrides({"length": "under30"}) == {"min_clip_s": 8.0, "max_clip_s": 30.0}
    assert validate_overrides({"length": "60to90"}) == {"min_clip_s": 60.0, "max_clip_s": 90.0}
    assert validate_overrides({"length": "auto"}) == {"min_clip_s": 15.0, "max_clip_s": 60.0}
    assert validate_overrides({"length": "bogus"}) == {}


def test_validate_overrides_trim():
    from clipper.config import validate_overrides
    assert validate_overrides({"trim": "0"}) == {"trim_silence": False}
    assert validate_overrides({"trim": "1"}) == {"trim_silence": True}
    assert validate_overrides({}) == {}


def test_keep_spans_and_remap():
    from clipper.trim import keep_spans, remap
    from clipper.config import Config
    cfg = Config()  # silence_max 0.5, silence_keep 0.15
    words = [
        {"word": "a", "start": 10.0, "end": 10.3},
        {"word": "b", "start": 10.3, "end": 10.6},
        {"word": "c", "start": 12.6, "end": 12.9},   # 2.0s gap before this
        {"word": "d", "start": 12.9, "end": 13.2},
    ]
    spans = keep_spans(words, 10.0, 13.5, cfg)
    assert len(spans) == 2, spans                      # the gap split the clip
    assert sum(b - a for a, b in spans) < 3.5          # time was removed
    rm = remap(words, spans)
    assert len(rm) == 4 and rm[0]["start"] < 0.2       # starts near zero
    for i in range(1, len(rm)):
        assert rm[i]["start"] - rm[i - 1]["end"] < 0.5  # no dead air left on new timeline
        assert rm[i]["start"] >= rm[i - 1]["start"]     # monotonic


def test_keep_spans_no_gaps_single_span():
    from clipper.trim import keep_spans, remap
    from clipper.config import Config
    cfg = Config()
    words = [{"word": "a", "start": 5.0, "end": 5.4}, {"word": "b", "start": 5.4, "end": 5.8}]
    spans = keep_spans(words, 5.0, 6.0, cfg)
    assert len(spans) == 1                              # gapless -> one span
    assert remap(words, spans)[0]["start"] < 0.2


def test_zoom_track():
    from clipper.crop import _zoom_track
    from clipper.config import Config
    cfg = Config()  # zoom_amount 0.08, zoom_gap 2.5
    fps, n = 30, 300  # 10s
    z = _zoom_track(n, fps, [1.0, 1.2, 5.0], cfg)  # 1.2 is within 2.5s of 1.0 -> skipped
    cap = 1.0 + cfg.zoom_amount
    assert z.min() >= 1.0 and z.max() <= cap + 1e-9   # stays in [1, 1+amount]
    assert z[0] == 1.0                                  # opens unzoomed
    assert z[30] > 1.0 + cfg.zoom_amount * 0.8          # peak at t=1.0
    assert z[150] > 1.0 + cfg.zoom_amount * 0.8         # peak at t=5.0
    assert z[90] < 1.01                                 # back to rest between punches (t=3.0)


def test_zoom_track_off():
    from clipper.crop import _zoom_track
    from clipper.config import Config
    z = _zoom_track(100, 30, None, Config())
    assert z.max() == 1.0 and z.min() == 1.0           # no triggers -> no zoom


def test_split_dims():
    from clipper.layout import split_dims
    top, bot = split_dims(1080, 1920, 0.5)
    assert top % 2 == 0 and bot % 2 == 0          # both even for h264
    assert top + bot == 1920                        # exactly fills the frame
    assert abs(top - 960) <= 2
    top2, bot2 = split_dims(1080, 1920, 0.6)
    assert top2 + bot2 == 1920 and top2 > top       # bigger head fraction
    # extreme ratios are clamped, still valid
    t3, b3 = split_dims(1080, 1920, 0.99)
    assert t3 + b3 == 1920 and b3 >= 2


def test_validate_overrides_layout():
    from clipper.config import validate_overrides
    assert validate_overrides({"layout": "split"}) == {"layout": "split"}
    assert validate_overrides({"layout": "fill"}) == {"layout": "fill"}
    assert validate_overrides({"layout": "bogus"}) == {}


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
        assert "WrapStyle: 0" in text                # captions wrap inside the frame
        assert "Stop wasting time" in text          # hook burned in
        assert accent in text                        # active word / keyword emphasis
        if style == "karaoke":
            dlg = [ln for ln in text.splitlines() if ln.startswith("Dialogue:")]
            assert any(ln.count(accent) >= 2 for ln in dlg), "keyword emphasis not applied independently of active word"


def run() -> None:
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")


if __name__ == "__main__":
    run()
