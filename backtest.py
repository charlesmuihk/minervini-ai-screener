import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os

WATCHLIST = [
    "NVDA","AAPL","MSFT","AMZN","GOOGL","META","AVGO","AMD","TSLA","ARM","PLTR","NFLX",
    "MU","MRVL","KLAC","LRCX","AMAT","ASML","MPWR","MCHP","NXPI","ONTO","ACLS","FORM",
    "CRWD","SNOW","DDOG","MDB","HUBS","APP","TTD","PANW","FTNT","ZS","NET","WDAY","ADSK","NOW","ADBE","TWLO","AI",
    "V","MA","COIN","SQ","PYPL","GS","MS","BAC","AXP","BLK","SCHW",
    "COST","BKNG","MELI","SHOP","UBER","ABNB","RBLX","DUOL","ELF","CELH","WING","CVNA",
    "LLY","VRTX","REGN","ISRG","AMGN","TMO","DHR",
    "RKLB","VRT","CLS","SPOT","EA","DKNG","MSTR","UPST","FRPT",
]

HOLD_DAYS_LIST = [7, 21, 63]
START_DATE     = "2020-01-01"
END_DATE       = "2025-12-31"
SCAN_INTERVAL  = 21
MIN_TREND      = 6
MIN_RS         = 70
MIN_EPS        = 0.20
MIN_REV        = 0.20
MAX_DIST       = 0.35

def check_trend(close, idx):
    if idx < 200: return 0, {}
    w = close.iloc[max(0,idx-365):idx+1]
    if len(w) < 200: return 0, {}
    cp    = w.iloc[-1]
    s50   = w.rolling(50).mean().iloc[-1]
    s150  = w.rolling(150).mean().iloc[-1]
    s200  = w.rolling(200).mean().iloc[-1]
    s200b = w.rolling(200).mean().iloc[-20] if len(w)>=220 else s200
    lo    = w.min()
    hi    = w.max()
    conds = {
        "C1": cp > s50,
        "C2": cp > s150,
        "C3": cp > s200,
        "C4": s150 > s200,
        "C5": s200 > s200b,
        "C6": s50 > s150,
        "C7": cp >= lo * 1.30,
        "C8": cp >= hi * 0.75,
    }
    dist = (cp - hi) / hi
    return sum(conds.values()), dist

def calc_rs_simple(stock_close, spy_close, idx):
    try:
        if idx < 200: return 0
        s3m = stock_close.iloc[idx] / stock_close.iloc[max(0,idx-63)] - 1
        m3m = spy_close.iloc[idx]   / spy_close.iloc[max(0,idx-63)]   - 1
        s6m = stock_close.iloc[idx] / stock_close.iloc[max(0,idx-126)] - 1
        m6m = spy_close.iloc[idx]   / spy_close.iloc[max(0,idx-126)]   - 1
        raw = 0.6*(s3m-m3m) + 0.4*(s6m-m6m)
        return min(99, max(1, int(50 + raw*200)))
    except:
        return 0

print("="*65)
print("  Minervini Backtest — 2020 to 2025")
print("="*65)
print(f"  Downloading {len(WATCHLIST)} stocks (5 years)...")
print()

spy_raw = yf.download("SPY", start=START_DATE, end=END_DATE, auto_adjust=True, progress=False)
spy_close = spy_raw["Close"].squeeze()

all_data = {}
for i, ticker in enumerate(WATCHLIST, 1):
    print(f"  [{i:2d}/{len(WATCHLIST)}] {ticker}...", end="\r", flush=True)
    try:
        df = yf.download(ticker, start=START_DATE, end=END_DATE, auto_adjust=True, progress=False)
        if len(df) > 200:
            all_data[ticker] = df["Close"].squeeze()
    except:
        pass

print(f"  Downloaded {len(all_data)} stocks successfully.          ")
print()

scan_dates = pd.date_range(start=START_DATE, end=END_DATE, freq=f"{SCAN_INTERVAL}D")
spy_aligned = spy_close.reindex(all_data.get("AAPL", spy_close).index, method="ffill")

trades = []

for scan_dt in scan_dates:
    signals = []
    for ticker, close in all_data.items():
        close_up_to = close[close.index <= scan_dt]
        spy_up_to   = spy_aligned[spy_aligned.index <= scan_dt]
        if len(close_up_to) < 210: continue
        idx   = len(close_up_to) - 1
        score, dist = check_trend(close_up_to, idx)
        rs    = calc_rs_simple(close_up_to, spy_up_to, idx)
        if score < MIN_TREND: continue
        if rs   < MIN_RS:     continue
        if abs(dist) > MAX_DIST: continue
        signals.append({"ticker": ticker, "score": score, "rs": rs, "dist": dist, "date": scan_dt})

    for sig in signals:
        ticker = sig["ticker"]
        close  = all_data[ticker]
        entry_prices = close[close.index > scan_dt]
        if len(entry_prices) == 0: continue
        entry_price = entry_prices.iloc[0]
        entry_date  = entry_prices.index[0]

        for hold_days in HOLD_DAYS_LIST:
            future = close[close.index > entry_date]
            if len(future) == 0: continue
            exit_idx   = min(hold_days, len(future)-1)
            exit_price = future.iloc[exit_idx]
            exit_date  = future.index[exit_idx]
            ret        = (exit_price / entry_price - 1) * 100

            spy_future = spy_aligned[spy_aligned.index > entry_date]
            spy_ret    = 0
            if len(spy_future) > exit_idx:
                spy_ret = (spy_future.iloc[exit_idx] / spy_future.iloc[0] - 1) * 100

            trades.append({
                "ticker":     ticker,
                "scan_date":  scan_dt.strftime("%Y-%m-%d"),
                "entry_date": entry_date.strftime("%Y-%m-%d"),
                "exit_date":  exit_date.strftime("%Y-%m-%d"),
                "hold_days":  hold_days,
                "entry":      round(float(entry_price), 2),
                "exit":       round(float(exit_price), 2),
                "return_pct": round(float(ret), 2),
                "spy_ret":    round(float(spy_ret), 2),
                "alpha":      round(float(ret - spy_ret), 2),
                "rs":         sig["rs"],
                "score":      sig["score"],
                "year":       scan_dt.year,
            })

df_trades = pd.DataFrame(trades)
print(f"  Total signals generated: {len(df_trades)}")
print()

def summarize(df, label):
    if len(df) == 0:
        print(f"  {label}: No data")
        return {}
    wins   = (df["return_pct"] > 0).sum()
    losses = (df["return_pct"] <= 0).sum()
    total  = len(df)
    win_rt = wins / total * 100
    avg_ret= df["return_pct"].mean()
    med_ret= df["return_pct"].median()
    avg_win= df[df["return_pct"]>0]["return_pct"].mean() if wins>0 else 0
    avg_los= df[df["return_pct"]<=0]["return_pct"].mean() if losses>0 else 0
    avg_alp= df["alpha"].mean()
    best   = df["return_pct"].max()
    worst  = df["return_pct"].min()
    return {
        "label": label, "total": total, "win_rate": win_rt,
        "avg_ret": avg_ret, "med_ret": med_ret,
        "avg_win": avg_win, "avg_loss": avg_los,
        "alpha": avg_alp, "best": best, "worst": worst,
    }

results = []
print("="*65)
print("  RESULTS BY HOLDING PERIOD")
print("="*65)
for hd in HOLD_DAYS_LIST:
    label = f"{hd}D ({hd//7}wk)" if hd < 30 else (f"{hd}D (1mo)" if hd<40 else f"{hd}D (3mo)")
    sub   = df_trades[df_trades["hold_days"] == hd]
    r     = summarize(sub, label)
    results.append(r)
    print(f"\n  Hold {label}:")
    print(f"    Signals   : {r['total']}")
    print(f"    Win Rate  : {r['win_rate']:.1f}%")
    print(f"    Avg Return: {r['avg_ret']:+.2f}%")
    print(f"    Median    : {r['med_ret']:+.2f}%")
    print(f"    Avg Win   : {r['avg_win']:+.2f}%")
    print(f"    Avg Loss  : {r['avg_loss']:+.2f}%")
    print(f"    vs SPY    : {r['alpha']:+.2f}% alpha")
    print(f"    Best      : {r['best']:+.2f}%")
    print(f"    Worst     : {r['worst']:+.2f}%")

print()
print("="*65)
print("  RESULTS BY YEAR (3-month hold)")
print("="*65)
sub63 = df_trades[df_trades["hold_days"]==63]
for yr in range(2020, 2026):
    sy = sub63[sub63["year"]==yr]
    if len(sy) == 0: continue
    wr = (sy["return_pct"]>0).mean()*100
    ar = sy["return_pct"].mean()
    print(f"  {yr}: {len(sy):3d} signals | Win {wr:.0f}% | Avg {ar:+.1f}%")

csv_file = "minervini_backtest_2020_2025.csv"
df_trades.to_csv(csv_file, index=False, encoding="utf-8-sig")
print()
print(f"  Full results saved: {csv_file}")
print("="*65)
input("\nPress Enter to close...")
