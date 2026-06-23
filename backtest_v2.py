import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os

WATCHLIST = [
    "NVDA","AAPL","MSFT","AMZN","GOOGL","META","AVGO","AMD","TSLA","ARM","PLTR","NFLX",
    "MU","MRVL","KLAC","LRCX","AMAT","ASML","MPWR","MCHP","NXPI","ONTO","ACLS","FORM",
    "CRWD","SNOW","DDOG","MDB","HUBS","APP","TTD","PANW","FTNT","ZS","NET","WDAY","ADSK",
    "NOW","ADBE","TWLO","AI","CLS","VRT","RKLB","DKNG","MSTR","UPST","FRPT","COIN",
    "V","MA","HOOD","SQ","PYPL","GS","MS","BAC","AXP","BLK","SCHW",
    "COST","BKNG","MELI","SHOP","UBER","ABNB","DUOL","ELF","CELH","WING","CVNA",
    "LLY","VRTX","REGN","ISRG","AMGN","TMO","DHR","SPOT","EA",
]

START_DATE    = "2020-01-01"
END_DATE      = "2025-12-31"
SCAN_INTERVAL = 21
HOLD_DAYS     = 63
MIN_TREND     = 6
MIN_RS        = 70
MIN_EPS       = 0.20
MIN_REV       = 0.20
MAX_DIST      = 0.35
STOP_PCT      = 0.08
VOL_MIN       = 0.8

def check_trend(close, idx):
    if idx < 200: return 0, 0
    w = close.iloc[max(0,idx-365):idx+1]
    if len(w) < 200: return 0, 0
    cp   = w.iloc[-1]
    s50  = w.rolling(50).mean().iloc[-1]
    s150 = w.rolling(150).mean().iloc[-1]
    s200 = w.rolling(200).mean().iloc[-1]
    s200b= w.rolling(200).mean().iloc[-20] if len(w)>=220 else s200
    lo   = w.min()
    hi   = w.max()
    conds = [
        cp > s50, cp > s150, cp > s200,
        s150 > s200, s200 > s200b, s50 > s150,
        cp >= lo * 1.30, cp >= hi * 0.75,
    ]
    dist = (cp - hi) / hi
    return sum(conds), dist

def calc_rs(stock_close, spy_close, idx):
    try:
        if idx < 200: return 0
        n = min(idx, 252)
        def p(c, a, b): return c.iloc[b] / c.iloc[a] - 1
        ss = (0.2*p(stock_close,idx-n,idx-int(n*.75))
            + 0.2*p(stock_close,idx-int(n*.75),idx-int(n*.5))
            + 0.3*p(stock_close,idx-int(n*.5),idx-int(n*.25))
            + 0.3*p(stock_close,idx-int(n*.25),idx))
        ms = (0.2*p(spy_close,idx-n,idx-int(n*.75))
            + 0.2*p(spy_close,idx-int(n*.75),idx-int(n*.5))
            + 0.3*p(spy_close,idx-int(n*.5),idx-int(n*.25))
            + 0.3*p(spy_close,idx-int(n*.25),idx))
        return min(99, max(1, int(50 + (ss - ms) * 300)))
    except: return 0

def calc_vol_ratio(volume, idx):
    try:
        if idx < 50: return 0
        avg50 = volume.iloc[max(0,idx-50):idx].mean()
        recent = volume.iloc[max(0,idx-5):idx].mean()
        return round(recent / avg50, 1) if avg50 > 0 else 0
    except: return 0

def detect_vcp(close, volume, idx):
    try:
        if idx < 30: return False
        c = close.iloc[idx-30:idx]
        v = volume.iloc[idx-30:idx]
        seg     = [c.iloc[i*10:(i+1)*10] for i in range(3)]
        vol_seg = [v.iloc[i*10:(i+1)*10] for i in range(3)]
        pullbacks = [(s.max()-s.min())/s.max() for s in seg]
        vol_trend = [vs.mean() for vs in vol_seg]
        contracting = pullbacks[0] > pullbacks[1] > pullbacks[2]
        vol_drying  = vol_trend[0] > vol_trend[1] > vol_trend[2]
        tight_range = pullbacks[2] < 0.05
        near_high   = c.iloc[-1] >= c.max() * 0.97
        return sum([contracting, vol_drying, tight_range, near_high]) >= 3
    except: return False

def run_backtest(data, spy_data):
    signals_v1 = []
    signals_v2 = []

    for ticker, df in data.items():
        if df is None or len(df) < 300: continue
        close  = df["Close"]
        volume = df["Volume"]

        scan_indices = range(200, len(close)-HOLD_DAYS, SCAN_INTERVAL)
        for idx in scan_indices:
            trend, dist = check_trend(close, idx)
            rs   = calc_rs(close, spy_data["Close"], idx)
            vol  = calc_vol_ratio(volume, idx)
            is_vcp = detect_vcp(close, volume, idx)

            entry = close.iloc[idx]
            exit_idx = min(idx + HOLD_DAYS, len(close)-1)
            exit_p   = close.iloc[exit_idx]

            # v1 base return (no stop)
            ret_v1 = (exit_p / entry - 1)

            # v2 return (with 8% stop loss)
            stop_price = entry * (1 - STOP_PCT)
            ret_v2 = ret_v1
            for d in range(1, exit_idx - idx):
                if idx + d >= len(close): break
                if close.iloc[idx+d] <= stop_price:
                    ret_v2 = -STOP_PCT
                    break

            date = close.index[idx]
            base_pass = (trend >= MIN_TREND and rs >= MIN_RS and
                        dist >= -MAX_DIST)

            # v1 signal
            if base_pass:
                signals_v1.append({
                    "ticker": ticker, "date": date,
                    "ret": ret_v1, "rs": rs,
                    "trend": trend, "dist": dist,
                })

            # v2 signal (adds vol filter)
            if base_pass and vol >= VOL_MIN:
                tier = "A" if (is_vcp and dist >= -0.05) or (dist >= -0.05 and rs >= 90) else (
                       "B" if dist >= -0.10 else "C")
                signals_v2.append({
                    "ticker": ticker, "date": date,
                    "ret": ret_v2, "ret_raw": ret_v1,
                    "rs": rs, "trend": trend,
                    "dist": dist, "vol": vol,
                    "is_vcp": is_vcp, "tier": tier,
                })

    return signals_v1, signals_v2

def print_results(signals_v1, signals_v2, spy_rets):
    def stats(sigs, label):
        if not sigs: return
        rets = [s["ret"] for s in sigs]
        wins = [r for r in rets if r > 0]
        loss = [r for r in rets if r <= 0]
        avg_spy = np.mean(spy_rets[:len(rets)]) if spy_rets else 0
        print(f"  {label}")
        print(f"    Signals   : {len(rets)}")
        print(f"    Win Rate  : {len(wins)/len(rets)*100:.1f}%")
        print(f"    Avg Return: {np.mean(rets)*100:+.2f}%")
        print(f"    Avg Win   : {np.mean(wins)*100:+.2f}%" if wins else "    Avg Win   : N/A")
        print(f"    Avg Loss  : {np.mean(loss)*100:+.2f}%" if loss else "    Avg Loss  : N/A")
        if wins and loss:
            ratio = abs(np.mean(wins)/np.mean(loss))
            print(f"    Win/Loss  : {ratio:.2f}x")
        print(f"    vs SPY    : {(np.mean(rets)-avg_spy)*100:+.2f}% alpha")
        print()

    print("=" * 60)
    print("  V1 vs V2 BACKTEST COMPARISON (2020-2025, 3mo hold)")
    print("=" * 60)
    print()
    stats(signals_v1, "VERSION 1 (baseline — no stop, no vol filter)")
    stats(signals_v2, "VERSION 2 (stop 8% + vol>=0.8x + tiers)")

    # V2 by tier
    for tier in ["A", "B", "C"]:
        tier_sigs = [s for s in signals_v2 if s["tier"] == tier]
        if tier_sigs:
            stats(tier_sigs, f"VERSION 2 — TIER {tier} only")

    # V2 VCP only
    vcp_sigs = [s for s in signals_v2 if s["is_vcp"]]
    if vcp_sigs:
        stats(vcp_sigs, "VERSION 2 — VCP signals only")

    # Year by year V2
    print("  V2 BY YEAR:")
    for year in range(2020, 2026):
        yr = [s for s in signals_v2 if s["date"].year == year]
        if yr:
            rets = [s["ret"] for s in yr]
            wins = sum(1 for r in rets if r > 0)
            print(f"    {year}: {len(yr):3d} signals | "
                  f"Win {wins/len(yr)*100:.0f}% | "
                  f"Avg {np.mean(rets)*100:+.1f}%")
    print("=" * 60)

if __name__ == "__main__":
    print("=" * 60)
    print("  Downloading data for backtest...")
    print("=" * 60)

    spy = yf.Ticker("SPY").history(start=START_DATE, end=END_DATE)
    spy_rets = []
    for i in range(200, len(spy)-HOLD_DAYS, SCAN_INTERVAL):
        r = spy["Close"].iloc[i+HOLD_DAYS] / spy["Close"].iloc[i] - 1
        spy_rets.append(r)

    data = {}
    for i, ticker in enumerate(WATCHLIST):
        print(f"  [{i+1:02d}/{len(WATCHLIST)}] {ticker}...", end=" ", flush=True)
        try:
            df = yf.Ticker(ticker).history(start=START_DATE, end=END_DATE)
            if len(df) > 300:
                data[ticker] = df
                print("OK")
            else:
                print("skip")
        except:
            print("error")

    print()
    print("  Running backtest...")
    signals_v1, signals_v2 = run_backtest(data, spy)
    print_results(signals_v1, signals_v2, spy_rets)

    out = os.path.expanduser("~/minervini-ai-screener/backtest_v2_results.csv")
    rows = []
    for s in signals_v2:
        rows.append({
            "ticker": s["ticker"],
            "date": s["date"].date(),
            "ret": round(s["ret"]*100, 2),
            "ret_raw": round(s["ret_raw"]*100, 2),
            "rs": s["rs"],
            "tier": s["tier"],
            "is_vcp": s["is_vcp"],
            "dist": round(s["dist"]*100, 1),
        })
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"  Saved: {out}")
    input("Press Enter to close...")
