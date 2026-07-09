# Warren Code Review — Minervini AI Screener

Date: 2026-07-09  
Repo: `charlesmuihk/minervini-ai-screener`  
Focus: why the scanner misses opportunities or finds them too far from pivot.

---

## Executive Summary

The current program is useful as a **strong-stock / trend-template screener**, but it is not yet a reliable **Minervini actionable buy-point scanner**.

Main root cause:

> The code mostly filters for stocks that are already strong / near 52-week highs, then tries to label VCP afterwards. It does not first identify local bases, pivots, buy zones, and pre-breakout tightening.

This explains Charles's symptom:

- Good opportunities are missed.
- When they appear, they are often already far from the true pivot.
- VCP count is too low.
- Historical pivot values are sometimes nonsensical.

---

## Evidence From Actual Test Run

I created a local venv and installed missing dependencies:

```bash
uv venv .venv
source .venv/bin/activate
uv pip install yfinance pandas numpy
```

Then I ran the scanner logic against current data.

### ANET Test

ANET is a good live example because Charles identified a possible VCP manually.

Result from current code:

```text
ANET in WATCHLIST? False
ANET cp 184.77 dist_hi% 0.0 trend 8 rs 93 vol 0.9
vcp False 1 None
cup False None
hist 147.06 2026-05-06 tight_recent histdist 25.6
```

Interpretation:

- ANET is not scanned at all because it is missing from `WATCHLIST`.
- If manually tested, it passes trend and RS strongly.
- But `detect_vcp()` returns `False` with score 1.
- The historical pivot is `$147.06`, not the true recent breakout area around `$181–182`.

This directly proves the user symptom.

---

## Root Causes

## 1. Watchlist is hardcoded and incomplete

File: `minervini_scanner.py`, lines 7–15

Current hardcoded list has 85 tickers but misses several important momentum / AI infrastructure names.

Examples missing from current watchlist:

- `ANET`
- `PENG`
- `ALAB`
- `CRWV`
- Many recent IPO / AI infrastructure leaders

Impact:

> If the ticker is not in `WATCHLIST`, no setup detection can happen. ANET was completely invisible.

Recommended fix:

- Move watchlist to `watchlist.csv` or `watchlist.yaml`.
- Add multiple universes: `core_growth`, `ai_infra`, `semis`, `software`, `ipo_leaders`, `moat_club`.
- Allow command-line option: `--tickers ANET,NVDA,PENG`.

---

## 2. VCP detection is too crude and misses real VCPs

File: `minervini_scanner.py`, lines 101–118

Current logic:

```python
recent = df.tail(30)
seg = [c.iloc[i*10:(i+1)*10] for i in range(3)]
pullbacks = [(s.max()-s.min())/s.max() for s in seg]
contracting = pullbacks[0] > pullbacks[1] > pullbacks[2]
vol_drying = vol_trend[0] > vol_trend[1] > vol_trend[2]
tight_range = pullbacks[2] < 0.05
near_high = c.iloc[-1] >= c.max() * 0.97
```

Problems:

- Uses arbitrary 10-day calendar blocks instead of swing highs / swing lows.
- Requires perfectly decreasing pullbacks across exactly 3 blocks.
- Requires volume to decrease in each 10-day block, which is too strict.
- Final block must be <5% range, often too tight for volatile growth stocks.
- Uses only 30 days; many proper VCPs form over 6–16 weeks.
- Pivot is just `seg[2].max()`, not actual resistance shelf.

Impact:

> A human can see ANET's contraction structure, but the algorithm cannot.

Recommended fix:

- Detect swing highs/lows using 3–5 day pivots.
- Measure 2–4 contractions over 6–16 weeks.
- Score contraction sequence, higher lows, final tightness, and volume dry-up.
- Return `vcp_score / 10`, not just boolean.

---

## 3. Pivot detection is not reliable

File: `minervini_scanner.py`, lines 149–202

Current `detect_historical_pivot()` scans from the 52-week low and finds a quiet 10-day zone after the low.

Example output:

```text
AMD hist pivot 204.83, current price 545.49, histdist +166.3%
MU hist pivot 399.55, current price 1000.30, histdist +150.4%
ANET hist pivot 147.06, current price 184.77, histdist +25.6%
```

Problem:

> These are not actionable pivots. They are old consolidation areas after a low.

Minervini pivot should be:

- The local resistance shelf on the right side of the current base.
- Usually the highest high of the final contraction / handle.
- Useful only if price is within roughly -3% to +5% of it.

Recommended fix:

- Replace historical pivot with local base pivot detection.
- Use recent 6–16 week base window.
- Identify base high, final contraction high, and resistance shelf.
- Add `distance_from_pivot` and `setup_status`.

---

## 4. The scanner finds breakouts too late because it lacks pre-pivot alerts

Current output focuses on stocks that already passed filters. It does not surface:

- Pivot approaching
- Setup forming
- Retest watch
- Buy zone
- Extended warning

Impact:

> If a stock is only shown after it has already broken out, Charles sees it too far from pivot.

Recommended setup statuses:

| Status | Rule |
|---|---|
| `Setup Forming` | VCP/base score decent, price 3–8% below pivot |
| `Pivot Approaching` | price within 0–3% below pivot |
| `Actionable Pivot` | price 0–5% above pivot and stop risk acceptable |
| `Retest Watch` | breakout happened; pullback to pivot zone on lower volume |
| `Extended` | price >5–8% above pivot |
| `Base Repair` | strong company but base too deep / loose |

---

## 5. Volume filter rejects the exact quiet setups Minervini wants

File: `minervini_scanner.py`, lines 23, 213–218, 262–269

Current rule:

```python
VOL_MIN = 0.8
vol_ratio = recent_5_day_avg_volume / avg_50_day_volume
passed requires vol_ratio >= 0.8
```

Problem:

- During VCP formation, lower volume can be good.
- Current rule can reject quiet, tight setups before breakout.
- Breakout volume and VCP dry-up are opposite concepts and must be separated.

Recommended fix:

Use two fields:

1. `quiet_volume_ratio`: during base / final contraction; lower is good.
2. `breakout_volume_ratio`: on breakout day; higher is good.

Rules:

- Setup forming: final contraction volume `<0.8x` average can be positive.
- Breakout confirmed: breakout day volume `>1.5x` average is positive.

---

## 6. Trend Template scoring is not exact Minervini template

File: `minervini_scanner.py`, lines 79–99

Current checks:

```python
checks = [
    cp > s150 and cp > s200,
    s150 > s200,
    s200 > s200_63,
    s50 > s150 and s50 > s200,
    cp > s50,
    cp >= lo52 * 1.25,
    cp >= hi52 * 0.75,
    cp >= hi52 * 0.72,
]
```

Issues:

- `cp > s150` and `cp > s200` are bundled into one point.
- `cp >= hi52 * 0.75` and `cp >= hi52 * 0.72` are mostly duplicate.
- Standard Minervini uses price at least 30% above 52-week low, not 25%.
- Should be 8 distinct conditions.

Recommended exact rules:

1. Price > 50MA
2. Price > 150MA
3. Price > 200MA
4. 50MA > 150MA
5. 50MA > 200MA
6. 200MA rising
7. Price ≥ 30% above 52-week low
8. Price within 25% of 52-week high

---

## 7. RS calculation saturates too many stocks at 99

File: `minervini_scanner.py`, lines 67–77

Current formula:

```python
return min(99, max(1, int(50 + (ss - ms) * 300)))
```

Problem:

- It is not a percentile ranking across the universe.
- Many stocks become `RS=99`, reducing usefulness.
- It is hard to rank candidates if half the list is 99.

Recommended fix:

- Calculate weighted 3/6/9/12 month relative returns for all scanned stocks.
- Rank them into percentile 1–99 after scanning the universe.
- Add `rs_new_high` if RS line is at/near new high.

---

## 8. Fundamental filter may reject valid setups due missing yfinance fields

File: `minervini_scanner.py`, lines 204–211 and 260–269

Current pass requires:

```python
eps_ok and revenue >= 20%
```

Problems:

- Yahoo `info` fields can be missing, stale, or inconsistent.
- Newer names / IPOs may not have clean EPS growth.
- Strong sales-growth leaders can be rejected if EPS unavailable.

Recommended fix:

- Keep fundamentals as score, not absolute gate for setup visibility.
- Separate `technical_setup_candidates` from `fundamental_quality_pass`.
- Show warning: `Fundamentals missing`, not hide the setup.

---

## 9. The report uses From High as a buyability proxy

Current tier logic mainly uses distance from 52-week high:

```python
if is_vcp and dist >= -5: tier A
elif dist >= -5 and rs >= 90: tier A
elif dist >= -10: tier B
else: tier C
```

Problem:

> Near 52-week high is not the same as near pivot.

A stock can be:

- Near high but extended from pivot.
- Far from 52-week high but near a valid local base pivot.
- Near pivot but not yet through the 52-week high.

Recommended fix:

Tier should use:

- `distance_from_pivot`
- `stop_risk_percent`
- `vcp_score`
- `volume context`
- `earnings risk`

---

## 10. Missing dependency and portability files

There is no `requirements.txt` / `pyproject.toml`.

Current import failed initially:

```text
ModuleNotFoundError: No module named 'yfinance'
```

Also the script saves to a machine-specific path:

```python
fpath = os.path.expanduser(f"~/minervini-ai-screener/{fname}")
desktop = "/mnt/c/Users/Wah Mui/Desktop"
```

Recommended fix:

- Add `requirements.txt`.
- Save reports relative to repo, e.g. `reports/minervini_YYYY-MM-DD.html`.
- Make Windows desktop auto-open optional via `--open`.

---

## Recommended Development Plan

## Phase 1 — Fix visibility and timing

1. Add `ANET`, `PENG`, `ALAB`, `CRWV` and other AI infrastructure names to watchlist.
2. Move watchlist to external file.
3. Add `setup_status`.
4. Add local pivot detection.
5. Add `distance_from_pivot`.
6. Add `extended_flag`.
7. Add `stop_risk_percent`.
8. Show candidates even if they are not full Tier A.

## Phase 2 — Replace VCP detection

1. Detect swing highs and lows.
2. Measure contraction depths.
3. Require 2–4 contractions.
4. Score VCP /10.
5. Add volume dry-up during final contraction.
6. Detect retest to pivot zone.

## Phase 3 — Improve ranking and execution

1. Replace RS formula with universe percentile.
2. Add earnings date risk.
3. Add ATR%.
4. Add position sizing.
5. Add alert categories:
   - Pivot approaching
   - Breakout confirmed
   - Retest entry
   - Extended warning
   - Failed breakout

---

## Immediate Patch Candidates

High-impact files:

- `minervini_scanner.py`

Specific functions to replace or add:

- Replace `detect_vcp()`
- Replace `detect_historical_pivot()` with local `detect_base_and_pivot()`
- Add `classify_setup_status()`
- Add `calc_atr()`
- Add external `load_watchlist()`
- Improve `check_trend()`
- Change `passed` logic so setup candidates can appear even if fundamentals are incomplete

---

## Warren Verdict

The program is a good v2 prototype, but it currently answers:

> “Which stocks are strong and near highs?”

It needs to answer:

> “Which leadership stocks are within a controlled-risk buy zone near a valid pivot?”

That is the core difference between a screener and a Minervini execution system.
