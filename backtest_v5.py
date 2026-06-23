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
STOP_PCT_BULL = 0.08
STOP_PCT_NEU  = 0.06
STOP_PCT_BEAR = 0.05
STOP_PCT_C    = 0.10
VOL_MIN       = 0.8
MIN_RS_BULL   = 70
MIN_RS_NEU    = 90
MIN_RS_BEAR   = 85
POS_BULL      = 1.0
POS_NEU       = 0.5
POS_BEAR      = 0.25

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


def get_spy_regime(spy_close, idx):
    if idx < 200: return "BEAR"
    cp   = spy_close.iloc[idx]
    s50  = spy_close.iloc[max(0,idx-50):idx].mean()
    s150 = spy_close.iloc[max(0,idx-150):idx].mean()
    s200 = spy_close.iloc[max(0,idx-200):idx].mean()
    score = sum([cp > s50, cp > s150, cp > s200, s150 > s200])
    if score >= 3: return "BULL"
    if score >= 2: return "NEUTRAL"
    return "BEAR"

def run_backtest(data, spy_data):
    signals_v1 = []
    signals_v2 = []
    signals_v3 = []
    signals_v4 = []
    signals_v5 = []
    spy_close_g = spy_data["Close"].reset_index(drop=True)
    spy_index = spy_data.index
    if hasattr(spy_index[0], "tzinfo") and spy_index[0].tzinfo is not None:
        spy_index = spy_index.tz_localize(None)

    for ticker, df in data.items():
        if df is None or len(df) < 300: continue
        close  = df["Close"]
        volume = df["Volume"]
        stock_index = close.index
        if hasattr(stock_index[0], "tzinfo") and stock_index[0].tzinfo is not None:
            stock_index = stock_index.tz_localize(None)

        for idx in range(200, len(close)-HOLD_DAYS, SCAN_INTERVAL):
            trend, dist = check_trend(close, idx)
            rs     = calc_rs(close, spy_data["Close"], idx)
            vol    = calc_vol_ratio(volume, idx)
            is_vcp = detect_vcp(close, volume, idx)

            entry    = close.iloc[idx]
            exit_idx = min(idx + HOLD_DAYS, len(close)-1)
            exit_p   = close.iloc[exit_idx]
            date     = stock_index[idx]
            ret_v1   = (exit_p / entry - 1)

            spy_idx = spy_index.searchsorted(date)
            spy_idx = min(spy_idx, len(spy_close_g)-1)
            regime  = get_spy_regime(spy_close_g, spy_idx)

            stop_8 = entry * (1 - STOP_PCT_BULL)
            ret_v2 = ret_v1
            for d in range(1, exit_idx - idx):
                if idx + d >= len(close): break
                if close.iloc[idx+d] <= stop_8:
                    ret_v2 = -STOP_PCT_BULL
                    break

            base_pass = (trend >= MIN_TREND and (rs or 0) >= MIN_RS and dist >= -MAX_DIST)

            if base_pass:
                signals_v1.append({"ticker":ticker,"date":date,"ret":ret_v1,"rs":rs,"trend":trend,"dist":dist})

            if base_pass and vol >= VOL_MIN:
                tier = "A" if (is_vcp and dist>=-0.05) or (dist>=-0.05 and (rs or 0)>=90) else ("B" if dist>=-0.10 else "C")
                signals_v2.append({"ticker":ticker,"date":date,"ret":ret_v2,"ret_raw":ret_v1,"rs":rs,"trend":trend,"dist":dist,"vol":vol,"is_vcp":is_vcp,"tier":tier})

            if base_pass and vol >= VOL_MIN and regime == "BULL":
                tier = "A" if (is_vcp and dist>=-0.05) or (dist>=-0.05 and (rs or 0)>=90) else ("B" if dist>=-0.10 else "C")
                ret_v3 = ret_v1
                for d in range(1, exit_idx - idx):
                    if idx + d >= len(close): break
                    if close.iloc[idx+d] <= stop_8:
                        ret_v3 = -STOP_PCT_BULL
                        break
                signals_v3.append({"ticker":ticker,"date":date,"ret":ret_v3,"ret_raw":ret_v1,"rs":rs,"trend":trend,"dist":dist,"vol":vol,"is_vcp":is_vcp,"tier":tier,"regime":regime})

            if regime == "BULL":
                rs_min = MIN_RS_BULL
                stop_pct = STOP_PCT_BULL
                pos_size = POS_BULL
            elif regime == "NEUTRAL":
                rs_min = MIN_RS_NEU
                stop_pct = STOP_PCT_NEU
                pos_size = POS_NEU
            else:
                rs_min = MIN_RS_BEAR
                stop_pct = STOP_PCT_BEAR
                pos_size = POS_BEAR

            v4_pass = (trend >= MIN_TREND and (rs or 0) >= MIN_RS and dist >= -MAX_DIST and vol >= VOL_MIN)
            if v4_pass:
                tier = "A" if (is_vcp and dist>=-0.05) or (dist>=-0.05 and (rs or 0)>=90) else ("B" if dist>=-0.10 else "C")
                sp = entry * (1 - STOP_PCT_BULL if regime=="BULL" else STOP_PCT_NEU if regime=="NEUTRAL" else STOP_PCT_BEAR)
                ret_v4r = ret_v1
                for d in range(1, exit_idx - idx):
                    if idx + d >= len(close): break
                    if close.iloc[idx+d] <= sp:
                        ret_v4r = -(STOP_PCT_BULL if regime=="BULL" else STOP_PCT_NEU if regime=="NEUTRAL" else STOP_PCT_BEAR)
                        break
                signals_v4.append({"ticker":ticker,"date":date,"ret":ret_v4r*pos_size,"ret_raw":ret_v4r,"rs":rs,"trend":trend,"dist":dist,"vol":vol,"is_vcp":is_vcp,"tier":tier,"regime":regime,"pos_size":pos_size})

            # V5: stricter NEUTRAL, VCP priority, tighter Tier C stop
            if regime == "BULL":
                rs_min5 = MIN_RS_BULL
                stop5   = STOP_PCT_BULL
                pos5    = POS_BULL
                tier_filter = True
            elif regime == "NEUTRAL":
                rs_min5 = MIN_RS_NEU
                stop5   = STOP_PCT_NEU
                pos5    = POS_NEU
                tier_filter = is_vcp or (rs or 0) >= 90
            else:  # BEAR
                rs_min5 = MIN_RS_BEAR
                stop5   = STOP_PCT_BEAR
                pos5    = POS_BEAR
                tier_filter = is_vcp or (rs or 0) >= MIN_RS_BEAR

            v5_pass = (
                trend >= MIN_TREND and
                (rs or 0) >= rs_min5 and
                dist >= -MAX_DIST and
                vol >= VOL_MIN and
                tier_filter
            )

            if v5_pass:
                tier = "A" if (is_vcp and dist>=-0.05) or (dist>=-0.05 and (rs or 0)>=90) else ("B" if dist>=-0.10 else "C")
                stop_price = entry * (1 - stop5)
                if tier == "C":
                    stop_price = entry * (1 - STOP_PCT_C)
                    stop5_used = STOP_PCT_C
                else:
                    stop5_used = stop5
                ret_v5r = ret_v1
                for d in range(1, exit_idx - idx):
                    if idx + d >= len(close): break
                    if close.iloc[idx+d] <= stop_price:
                        ret_v5r = -stop5_used
                        break
                ret_v5 = ret_v5r * pos5
                signals_v5.append({
                    "ticker": ticker, "date": date,
                    "ret": ret_v5, "ret_raw": ret_v5r,
                    "rs": rs, "trend": trend, "dist": dist,
                    "vol": vol, "is_vcp": is_vcp,
                    "tier": tier, "regime": regime,
                    "pos_size": pos5,
                })

    return signals_v1, signals_v2, signals_v3, signals_v4, signals_v5


def print_results(signals_v1, signals_v2, signals_v3, signals_v4, signals_v5, spy_rets):
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
    print("  V1 to V5 BACKTEST COMPARISON (2020-2025, 3mo hold)")
    print("=" * 60)
    print()
    stats(signals_v1, "VERSION 1 (baseline — no stop, no vol filter)")
    stats(signals_v2, "VERSION 2 (stop 8% + vol>=0.8x + tiers)")
    stats(signals_v3, "VERSION 3 (v2 + BULL only + tier C stop 12%)")
    stats(signals_v4, "VERSION 4 (regime-aware: BULL 8% / NEU 7% / BEAR 5% stop + sizing)")
    stats(signals_v5, "VERSION 5 (v4 + NEU RS>=90 + VCP priority + tier C stop 10%)")
    print("  --- V5 BY REGIME ---")
    for reg in ["BULL", "NEUTRAL", "BEAR"]:
        rs = [s for s in signals_v5 if s["regime"]==reg]
        if rs: stats(rs, f"V5 — {reg} only")
    vcp5 = [s for s in signals_v5 if s["is_vcp"]]
    if vcp5: stats(vcp5, "V5 — VCP only")

    # V4 by regime
    print("  --- V4 BY REGIME ---")
    for reg in ["BULL", "NEUTRAL", "BEAR"]:
        reg_sigs = [s for s in signals_v4 if s["regime"]==reg]
        if reg_sigs:
            stats(reg_sigs, f"VERSION 4 — {reg} market only")

    # V4 by tier
    print("  --- V4 BY TIER ---")
    for tier in ["A", "B", "C"]:
        tier_sigs = [s for s in signals_v4 if s["tier"]==tier]
        if tier_sigs:
            stats(tier_sigs, f"VERSION 4 — TIER {tier} only")

    vcp_v4 = [s for s in signals_v4 if s["is_vcp"]]
    if vcp_v4:
        stats(vcp_v4, "VERSION 4 — VCP only")

    # V3 by tier
    print("  --- V3 BREAKDOWN ---")
    for tier in ["A", "B", "C"]:
        tier_sigs = [s for s in signals_v3 if s["tier"] == tier]
        if tier_sigs:
            stats(tier_sigs, f"VERSION 3 — TIER {tier} only")

    # V3 VCP only
    vcp_sigs = [s for s in signals_v3 if s["is_vcp"]]
    if vcp_sigs:
        stats(vcp_sigs, "VERSION 3 — VCP signals only")

    # Year by year comparison
    print("  YEAR BY YEAR COMPARISON:")
    print(f"  {'Year':<6} {'V1 Avg':>8} {'V2 Avg':>8} {'V4 Avg':>8} {'V5 Avg':>8} {'V5 Win':>8}")
    print("  " + "-" * 58)
    for year in range(2020, 2026):
        y1 = [s for s in signals_v1 if s["date"].year == year]
        y2 = [s for s in signals_v2 if s["date"].year == year]
        y3 = [s for s in signals_v3 if s["date"].year == year]
        def yr_stats(sigs):
            if not sigs: return "  N/A", "   N/A"
            rets = [s["ret"] for s in sigs]
            win = f"{sum(1 for r in rets if r>0)/len(rets)*100:.0f}%({len(sigs)})"
            avg = f"{np.mean(rets)*100:+.1f}%"
            return win, avg
        y4 = [s for s in signals_v4 if s["date"].year == year]
        y5 = [s for s in signals_v5 if s["date"].year == year]
        w1,a1 = yr_stats(y1)
        w2,a2 = yr_stats(y2)
        w4,a4 = yr_stats(y4)
        w5,a5 = yr_stats(y5)
        print(f"  {year:<6} {a1:>8} {a2:>8} {a4:>8} {a5:>8} {w5:>8}")
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
    signals_v1, signals_v2, signals_v3, signals_v4, signals_v5 = run_backtest(data, spy)
    print(f"  DEBUG: v1={len(signals_v1)} v2={len(signals_v2)} v4={len(signals_v4)} v5={len(signals_v5)}")
    print_results(signals_v1, signals_v2, signals_v3, signals_v4, signals_v5, spy_rets)

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
