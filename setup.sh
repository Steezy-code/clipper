#!/usr/bin/env bash
# clipper setup - macOS / Linux
# Run from the project folder:  ./setup.sh
set -e
MODEL="${CLIPPER_MODEL:-qwen3:8b}"

echo ""
echo "=== clipper setup ==="

# 1. Python
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 not found. Install Python 3.10+ and re-run." >&2
  exit 1
fi

# 2. venv + deps
[ -d .venv ] || python3 -m venv .venv
./.venv/bin/python -m pip install --quiet --upgrade pip
./.venv/bin/python -m pip install --quiet -r requirements.txt
echo "Python dependencies installed."

# 3. ffmpeg
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg not found. Install it:"
  echo "   macOS:  brew install ffmpeg"
  echo "   Linux:  sudo apt install ffmpeg"
else
  echo "ffmpeg found."
fi

# 4. Ollama model
if command -v ollama >/dev/null 2>&1; then
  echo "Pulling Ollama model: $MODEL"
  ollama pull "$MODEL"
else
  echo "Ollama not found. Install from ollama.com, then run: ollama pull $MODEL"
fi

echo ""
echo "Done. Start it with:"
echo "  ./.venv/bin/python app.py"
echo "Then open http://localhost:8765"
echo ""
