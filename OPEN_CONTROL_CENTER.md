# How to Open Minervini Control Center v1.0

## Easiest: create a Windows Desktop icon

Open **WSL / Ubuntu** and run:

```bash
cd ~/minervini-ai-screener
git pull origin main
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(wslpath -w Create_Control_Center_Desktop_Shortcut.ps1)"
```

Then double-click this Windows Desktop shortcut:

```text
Minervini Control Center
```

It opens:

```text
http://localhost:8501
```

## Manual WSL launch

```bash
cd ~/minervini-ai-screener
git pull origin main
source .venv/bin/activate
uv pip install -r requirements.txt
python -m streamlit run control_center.py --server.address 0.0.0.0 --server.port 8501
```

Then open your Windows browser:

```text
http://localhost:8501
```

## If the page does not open

1. Keep the WSL/Ubuntu terminal window running.
2. Open browser manually to `http://localhost:8501`.
3. If port 8501 is busy, stop old Streamlit windows or restart WSL.

## Files

- `control_center.py` — Streamlit web app
- `Minervini_Control_Center.bat` — batch launcher if you browse to the repo folder
- `Create_Control_Center_Desktop_Shortcut.ps1` — creates the Desktop shortcut
