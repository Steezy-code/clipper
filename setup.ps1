# clipper setup - Windows / PowerShell
# Run from the project folder:  ./setup.ps1
$ErrorActionPreference = "Stop"
$Model = if ($env:CLIPPER_MODEL) { $env:CLIPPER_MODEL } else { "qwen3:8b" }

Write-Host "`n=== clipper setup ===" -ForegroundColor Cyan

# 1. Python
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  Write-Host "Python not found. Install Python 3.10+ from python.org, then re-run." -ForegroundColor Red
  exit 1
}

# 2. venv + deps
if (-not (Test-Path ".venv")) { python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
& .\.venv\Scripts\python.exe -m pip install --quiet -r requirements.txt
Write-Host "Python dependencies installed." -ForegroundColor Green

# 3. ffmpeg
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
  Write-Host "ffmpeg not found. Install it with:  winget install Gyan.FFmpeg" -ForegroundColor Yellow
  Write-Host "(then open a new terminal so PATH refreshes)" -ForegroundColor Yellow
} else {
  Write-Host "ffmpeg found." -ForegroundColor Green
}

# 4. Ollama model
if (Get-Command ollama -ErrorAction SilentlyContinue) {
  Write-Host "Pulling Ollama model: $Model" -ForegroundColor Cyan
  ollama pull $Model
} else {
  Write-Host "Ollama not found. Install from ollama.com, then run: ollama pull $Model" -ForegroundColor Yellow
}

Write-Host "`nDone. Start it with:" -ForegroundColor Green
Write-Host "  .\.venv\Scripts\python.exe app.py" -ForegroundColor White
Write-Host "Then open http://localhost:8765`n"
