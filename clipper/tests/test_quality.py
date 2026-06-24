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
