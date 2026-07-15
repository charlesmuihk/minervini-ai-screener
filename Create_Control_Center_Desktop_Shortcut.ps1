$ErrorActionPreference = "Stop"

$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "Minervini Control Center.lnk"
$wslExe = Join-Path $env:SystemRoot "System32\wsl.exe"

if (!(Test-Path $wslExe)) {
    throw "Cannot find wsl.exe. Please install/enable WSL first."
}

# This command runs inside WSL. It accepts either the normal Charles path
# (~/minervini-ai-screener) or Warren's workspace path used during development.
$wslCommand = "set -e; " +
    "if [ -d ~/minervini-ai-screener ]; then cd ~/minervini-ai-screener; " +
    "elif [ -d /opt/data/workspace/minervini-ai-screener ]; then cd /opt/data/workspace/minervini-ai-screener; " +
    "else echo 'Repo not found. In WSL run: git clone https://github.com/charlesmuihk/minervini-ai-screener.git ~/minervini-ai-screener'; read -p 'Press Enter to close...'; exit 1; fi; " +
    "git pull --ff-only origin main || true; " +
    "if [ ! -d .venv ]; then if command -v uv >/dev/null 2>&1; then uv venv .venv && . .venv/bin/activate && uv pip install -r requirements.txt; else python3 -m venv .venv && . .venv/bin/activate && python -m pip install -r requirements.txt; fi; else . .venv/bin/activate; fi; " +
    "if ! python -c 'import streamlit' >/dev/null 2>&1; then if command -v uv >/dev/null 2>&1; then uv pip install -r requirements.txt; else python -m ensurepip --upgrade && python -m pip install -r requirements.txt; fi; fi; " +
    "if command -v powershell.exe >/dev/null 2>&1; then powershell.exe -NoProfile -Command 'Start-Process http://localhost:8501' >/dev/null 2>&1 || true; fi; " +
    "python -m streamlit run control_center.py --server.address 0.0.0.0 --server.port 8501"

$wsh = New-Object -ComObject WScript.Shell
$shortcut = $wsh.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $wslExe
$shortcut.Arguments = "bash -lc `"$wslCommand`""
$shortcut.WorkingDirectory = $desktop
$shortcut.Description = "Open Minervini Scanner Control Center v1.0"
$shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,167"
$shortcut.Save()

Write-Host "Created desktop shortcut: $shortcutPath"
Write-Host "Double-click 'Minervini Control Center' on your Desktop to open http://localhost:8501"
