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
