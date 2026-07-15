@echo off
setlocal
title Minervini Control Center

echo ============================================================
echo   Minervini Control Center
echo ============================================================
echo.

REM Run the Streamlit control center inside WSL and open it in the browser.
wsl.exe bash -lc "set -e; if [ -d ~/minervini-ai-screener ]; then cd ~/minervini-ai-screener; elif [ -d /opt/data/workspace/minervini-ai-screener ]; then cd /opt/data/workspace/minervini-ai-screener; else echo 'Repo not found. Please clone charlesmuihk/minervini-ai-screener into ~/minervini-ai-screener'; exit 1; fi; if [ ! -d .venv ]; then if command -v uv >/dev/null 2>&1; then uv venv .venv && . .venv/bin/activate && uv pip install -r requirements.txt; else python3 -m venv .venv && . .venv/bin/activate && python -m pip install -r requirements.txt; fi; else . .venv/bin/activate; fi; if ! python -c 'import streamlit' >/dev/null 2>&1; then if command -v uv >/dev/null 2>&1; then uv pip install -r requirements.txt; else python -m ensurepip --upgrade && python -m pip install -r requirements.txt; fi; fi; mkdir -p .streamlit && printf '[browser]\\ngatherUsageStats = false\\n' > .streamlit/config.toml; if command -v powershell.exe >/dev/null 2>&1; then powershell.exe -NoProfile -Command 'Start-Process http://localhost:8501' >/dev/null 2>&1 || true; fi; STREAMLIT_BROWSER_GATHER_USAGE_STATS=false python -m streamlit run control_center.py --server.address 0.0.0.0 --server.port 8501 --server.headless true"

echo.
echo Control Center stopped.
pause
