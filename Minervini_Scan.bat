@echo off
setlocal
title Minervini Scanner v3.1

echo ============================================================
echo   Minervini Scanner v3.1
echo ============================================================
echo.

REM Run inside WSL. It first tries the common home folder path, then the Hermes workspace path.
wsl.exe bash -lc "set -e; if [ -d ~/minervini-ai-screener ]; then cd ~/minervini-ai-screener; elif [ -d /opt/data/workspace/minervini-ai-screener ]; then cd /opt/data/workspace/minervini-ai-screener; else echo 'Repo not found. Please clone charlesmuihk/minervini-ai-screener into ~/minervini-ai-screener'; exit 1; fi; if [ ! -d .venv ]; then if command -v uv >/dev/null 2>&1; then uv venv .venv && . .venv/bin/activate && uv pip install -r requirements.txt; else python3 -m venv .venv && . .venv/bin/activate && python -m pip install -r requirements.txt; fi; else . .venv/bin/activate; fi; python minervini_scanner.py"

echo.
echo Done. If the browser did not open, check the reports folder in WSL.
pause
