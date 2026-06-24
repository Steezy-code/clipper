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


def run() -> None:
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")


if __name__ == "__main__":
    run()
