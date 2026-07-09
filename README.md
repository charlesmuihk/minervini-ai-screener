# Minervini Scanner — USIC 2026

## 每次使用

### 方法 A：Windows 桌面 icon / shortcut

如果你想像之前 Claude 幫你整的 icon 一樣，雙擊便自動跑 scanner：

1. 在 Windows File Explorer 打開 repo folder
2. 右鍵 `create_windows_shortcut.ps1` → **Run with PowerShell**
3. Desktop 會出現：`Minervini Scanner v3.0`
4. 之後雙擊這個 icon 即可自動在 WSL 跑 scanner，並打開最新 HTML report

如果不想建立 `.lnk` shortcut，也可以直接雙擊：

```text
Minervini_Scan.bat
```

### 方法 B：WSL terminal 手動執行

```bash
python minervini_scanner.py
```

報告會輸出到：

```text
reports/minervini_YYYY-MM-DD.html
```

如在 Charles 的 Windows/WSL 桌面環境執行，程式會自動複製到 Desktop 並開瀏覽器；其他環境則只保存報告。

## 檔案說明

- `minervini_scanner.py`  主掃描程式
- `watchlist.csv`        可自行編輯的股票清單
- `tests/`               Regression tests
- `reports/`             每次掃描結果報告（HTML，不納入 git）
- `backtest.py`          回測程式（歷史驗證）

## v3.0 系統功能

- 8條 Minervini Trend Template
- **RS Percentile Ranking**：先掃完整 universe，再做 1–99 percentile ranking，避免大量股票同時顯示 RS=99
- **External Watchlist**：使用 `watchlist.csv`，不用修改 Python code 就可加 ticker
- **Local Pivot Detection**：以最近 base / right-side resistance shelf 判斷 pivot，不再只看 52週高位
- **Setup Status**：Actionable Pivot / Retest Watch / Pivot Approaching / Setup Forming / Extended / Base Repair
- **VCP Contraction Details**：顯示 VCP score 及最近 contraction depth
- **Earnings Risk**：High / Medium / Watch / Low
- **Position Sizing**：以 portfolio risk 及 stop distance 計算建議 shares / position value
- 市場環境燈號 BULL / NEUTRAL / BEAR
- 自動生成 HTML 報告

## 安裝

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

或用 uv：

```bash
uv venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

## 測試

```bash
pytest tests -q
```

## 篩選邏輯

- Trend Score 6/8 以上
- RS Percentile 70 以上
- EPS 或營收成長 20% 以上；若 fundamentals 缺失但技術 setup 明確，仍可顯示為候選
- 距52週高點 35% 以內
- Earnings risk 若為 High，避免新 entry
- Setup 狀態優先：Pivot Approaching / Actionable Pivot / Retest Watch 比單純 near high 更重要

## Setup Status 說明

| Status | 意義 |
|---|---|
| Actionable Pivot | 剛突破或在 pivot 上方 0–5%，且 stop risk 可控 |
| Retest Watch | 突破後回踩 pivot 附近，成交較安靜 |
| Pivot Approaching | pivot 下方 0–3%，準備觀察 |
| Setup Forming | pivot 下方 3–8%，setup 正形成 |
| Extended | 離 pivot 太遠，避免追高 |
| Base Repair | 強股但 base / stop risk 未修好 |
| Leadership Candidate | 強股但暫未有明確買點 |

## 重要提醒

這是研究工具，不是投資建議。Minervini-style trading 的核心是：

> Find leaders, wait near pivot, control the loss, and size by risk.
