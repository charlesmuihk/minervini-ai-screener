import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
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
INITIAL_CAP   = 100000
SCAN_INTERVAL = 21
HOLD_DAYS     = 126

# Position rules by regime
REGIME_RULES = {
    "BULL":    {"max_pos": 4, "pos_pct": 0.25, "stop": 0.08, "min_rs": 70,  "vcp_only": False},
    "NEUTRAL": {"max_pos": 2, "pos_pct": 0.15, "stop": 0.06, "min_rs": 90,  "vcp_only": True},
    "BEAR":    {"max_pos": 1, "pos_pct": 0.10, "stop": 0.05, "min_rs": 90,  "vcp_only": True},
}

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

def check_trend(close, idx):
    if idx < 200: return 0, 0
    w = close.iloc[max(0,idx-365):idx+1]
    if len(w) < 200: return 0, 0
    cp   = w.iloc[-1]
    s50  = w.rolling(50).mean().iloc[-1]
    s150 = w.rolling(150).mean().iloc[-1]
    s200 = w.rolling(200).mean().iloc[-1]
    s200b= w.rolling(200).mean().iloc[-20] if len(w)>=220 else s200
    lo   = w.min(); hi = w.max()
    conds = [cp>s50, cp>s150, cp>s200, s150>s200, s200>s200b, s50>s150, cp>=lo*1.30, cp>=hi*0.75]
    return sum(conds), (cp-hi)/hi

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
        avg50  = volume.iloc[max(0,idx-50):idx].mean()
        recent = volume.iloc[max(0,idx-5):idx].mean()
        return round(recent/avg50, 1) if avg50 > 0 else 0
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

def score_stock(rs, dist, is_vcp, trend):
    score = 0
    score += min(rs, 99) * 0.4
    score += (1 + dist) * 20
    score += 15 if is_vcp else 0
    score += trend * 2
    return score

def run_portfolio_sim(data, spy_data):
    spy_close = spy_data["Close"].reset_index(drop=True)
    spy_index = spy_data.index
    if hasattr(spy_index[0], "tzinfo") and spy_index[0].tzinfo is not None:
        spy_index = spy_index.tz_localize(None)

    all_dates = sorted(set(
        d.date() for df in data.values() if df is not None
        for d in df.index
    ))

    capital = INITIAL_CAP
    portfolio = {}
    trades = []
    equity_curve = []
    scan_dates = all_dates[200::SCAN_INTERVAL]

    for scan_date in scan_dates:
        spy_pos = spy_index.searchsorted(pd.Timestamp(scan_date))
        spy_pos = min(spy_pos, len(spy_close)-1)
        regime  = get_spy_regime(spy_close, spy_pos)
        rules   = REGIME_RULES[regime]

        exited = []
        for ticker, pos in portfolio.items():
            if scan_date >= pos["exit_date"]:
                df = data.get(ticker)
                if df is None: continue
                close = df["Close"]
                si = close.index
                if hasattr(si[0], "tzinfo") and si[0].tzinfo is not None:
                    si = si.tz_localize(None)
                ep = min(si.searchsorted(pd.Timestamp(scan_date)), len(close)-1)
                exit_price = close.iloc[ep]
                pnl = (exit_price - pos["entry"]) * pos["shares"]
                capital += pos["cost"] + pnl
                trades.append({"ticker":ticker,"entry_date":pos["entry_date"],"exit_date":scan_date,
                    "entry":pos["entry"],"exit":round(exit_price,2),
                    "ret":round((exit_price/pos["entry"]-1)*100,2),
                    "regime":pos["regime"],"is_vcp":pos["is_vcp"],"tier":pos["tier"],"exit_reason":"time"})
                exited.append(ticker)
        for t in exited: del portfolio[t]

        stopped = []
        for ticker, pos in portfolio.items():
            df = data.get(ticker)
            if df is None: continue
            close = df["Close"]
            si = close.index
            if hasattr(si[0], "tzinfo") and si[0].tzinfo is not None:
                si = si.tz_localize(None)
            cp = min(si.searchsorted(pd.Timestamp(scan_date)), len(close)-1)
            cur_price = close.iloc[cp]
            if cur_price <= pos["stop_price"]:
                pnl = (cur_price - pos["entry"]) * pos["shares"]
                capital += pos["cost"] + pnl
                trades.append({"ticker":ticker,"entry_date":pos["entry_date"],"exit_date":scan_date,
                    "entry":pos["entry"],"exit":round(cur_price,2),
                    "ret":round((cur_price/pos["entry"]-1)*100,2),
                    "regime":pos["regime"],"is_vcp":pos["is_vcp"],"tier":pos["tier"],"exit_reason":"stop"})
                stopped.append(ticker)
        for t in stopped: del portfolio[t]

        candidates = []
        for ticker, df in data.items():
            if ticker in portfolio or df is None or len(df) < 300: continue
            close  = df["Close"]
            volume = df["Volume"]
            si = close.index
            if hasattr(si[0], "tzinfo") and si[0].tzinfo is not None:
                si = si.tz_localize(None)
            idx = si.searchsorted(pd.Timestamp(scan_date))
            if idx < 200 or idx >= len(close): continue
            trend, dist = check_trend(close, idx)
            rs     = calc_rs(close, spy_data["Close"], idx)
            vol    = calc_vol_ratio(volume, idx)
            is_vcp = detect_vcp(close, volume, idx)
            if trend < 6: continue
            if (rs or 0) < rules["min_rs"]: continue
            if dist < -0.35: continue
            if vol < 0.8: continue
            if rules["vcp_only"] and not is_vcp: continue
            # Exclude Tier B unless VCP
            pre_tier = "A" if (is_vcp and dist>=-0.05) or (dist>=-0.05 and (rs or 0)>=90) else ("B" if dist>=-0.10 else "C")
            if pre_tier == "B" and not is_vcp: continue
            tier = "A" if (is_vcp and dist>=-0.05) or (dist>=-0.05 and (rs or 0)>=90) else ("B" if dist>=-0.10 else "C")
            sc = score_stock(rs or 0, dist, is_vcp, trend)
            candidates.append({"ticker":ticker,"score":sc,"rs":rs,"dist":dist,"is_vcp":is_vcp,"tier":tier,"idx":idx,"close":close})

        candidates.sort(key=lambda x: -x["score"])
        slots = rules["max_pos"] - len(portfolio)

        for c in candidates[:slots]:
            if capital <= 0: break
            pos_cash = INITIAL_CAP * rules["pos_pct"]
            if pos_cash > capital: pos_cash = capital
            entry_price = c["close"].iloc[c["idx"]]
            shares = int(pos_cash / entry_price)
            if shares <= 0: continue
            cost = shares * entry_price
            stop_price = entry_price * (1 - rules["stop"])
            exit_date = (pd.Timestamp(scan_date) + pd.Timedelta(days=HOLD_DAYS)).date()
            portfolio[c["ticker"]] = {
                "entry":entry_price,"shares":shares,"cost":cost,
                "stop_price":stop_price,"entry_date":scan_date,
                "exit_date":exit_date,"regime":regime,
                "is_vcp":c["is_vcp"],"tier":c["tier"],
            }
            capital -= cost

        port_value = capital
        for ticker, pos in portfolio.items():
            df = data.get(ticker)
            if df is None: continue
            close = df["Close"]
            si = close.index
            if hasattr(si[0], "tzinfo") and si[0].tzinfo is not None:
                si = si.tz_localize(None)
            cp = min(si.searchsorted(pd.Timestamp(scan_date)), len(close)-1)
            port_value += close.iloc[cp] * pos["shares"]

        equity_curve.append({"date":scan_date,"equity":port_value,"regime":regime,"positions":len(portfolio)})

    return trades, equity_curve

def print_portfolio_results(trades, equity_curve):
    if not trades:
        print("No trades executed")
        return

    df = pd.DataFrame(trades)
    ec = pd.DataFrame(equity_curve)

    total_ret = (ec["equity"].iloc[-1] / INITIAL_CAP - 1) * 100
    wins  = df[df["ret"] > 0]
    loss  = df[df["ret"] <= 0]
    stops = df[df["exit_reason"] == "stop"]

    print("=" * 60)
    print("  PORTFOLIO SIMULATION v2 RESULTS (2020-2025)")
    print("  Minervini Concentrated Portfolio Strategy")
    print("=" * 60)
    print(f"  Initial Capital : ${INITIAL_CAP:,}")
    print(f"  Final Capital   : ${ec['equity'].iloc[-1]:,.0f}")
    print(f"  Total Return    : {total_ret:+.1f}%")
    print(f"  Total Trades    : {len(df)}")
    print(f"  Win Rate        : {len(wins)/len(df)*100:.1f}%")
    print(f"  Avg Win         : {wins['ret'].mean():+.1f}%" if len(wins) else "  Avg Win        : N/A")
    print(f"  Avg Loss        : {loss['ret'].mean():+.1f}%" if len(loss) else "  Avg Loss        : N/A")
    if len(wins) and len(loss):
        print(f"  Win/Loss Ratio  : {abs(wins['ret'].mean()/loss['ret'].mean()):.2f}x")
    print(f"  Stop Outs       : {len(stops)} ({len(stops)/len(df)*100:.0f}% of trades)")
    print()

    print("  BY REGIME:")
    for reg in ["BULL", "NEUTRAL", "BEAR"]:
        r = df[df["regime"]==reg]
        if len(r):
            w = r[r["ret"]>0]
            print(f"    {reg:<8}: {len(r):3d} trades | Win {len(w)/len(r)*100:.0f}% | Avg {r['ret'].mean():+.1f}%")
    print()

    print("  BY TIER:")
    for tier in ["A","B","C"]:
        t = df[df["tier"]==tier]
        if len(t):
            w = t[t["ret"]>0]
            print(f"    Tier {tier}   : {len(t):3d} trades | Win {len(w)/len(t)*100:.0f}% | Avg {t['ret'].mean():+.1f}%")
    print()

    vcp = df[df["is_vcp"]==True]
    if len(vcp):
        w = vcp[vcp["ret"]>0]
        print(f"  VCP trades  : {len(vcp):3d} trades | Win {len(w)/len(vcp)*100:.0f}% | Avg {vcp['ret'].mean():+.1f}%")
    print()

    print("  BY YEAR:")
    df["year"] = pd.to_datetime(df["entry_date"]).dt.year
    ec["year"] = pd.to_datetime(ec["date"]).dt.year
    for year in range(2020, 2026):
        yr = df[df["year"]==year]
        if len(yr):
            w = yr[yr["ret"]>0]
            yr_start = ec[ec["year"]==year]["equity"].iloc[0] if len(ec[ec["year"]==year]) else INITIAL_CAP
            yr_end   = ec[ec["year"]==year]["equity"].iloc[-1] if len(ec[ec["year"]==year]) else INITIAL_CAP
            yr_ret   = (yr_end/yr_start - 1)*100
            print(f"    {year}: {len(yr):3d} trades | Win {len(w)/len(yr)*100:.0f}% | Avg {yr['ret'].mean():+.1f}% | Portfolio {yr_ret:+.1f}%")
    print()

    print("  TOP 10 TRADES:")
    top = df.nlargest(10, "ret")[["ticker","entry_date","ret","regime","tier","is_vcp","exit_reason"]]
    for _, row in top.iterrows():
        vcp_tag = "[VCP]" if row["is_vcp"] else ""
        print(f"    {row['ticker']:<6} {str(row['entry_date']):<12} {row['ret']:+.1f}% {row['regime']:<8} Tier{row['tier']} {vcp_tag}")
    print()

    print("  WORST 5 TRADES:")
    bot = df.nsmallest(5, "ret")[["ticker","entry_date","ret","regime","tier","exit_reason"]]
    for _, row in bot.iterrows():
        print(f"    {row['ticker']:<6} {str(row['entry_date']):<12} {row['ret']:+.1f}% {row['regime']:<8} Tier{row['tier']} [{row['exit_reason']}]")
    print("=" * 60)

    out = os.path.expanduser("~/minervini-ai-screener/portfolio_trades.csv")
    df.to_csv(out, index=False)
    print(f"  Trades saved: {out}")


if __name__ == "__main__":
    print("=" * 60)
    print("  Portfolio Simulation v2 — Tier A+VCP only, 126-day hold")
    print("=" * 60)
    print("  Downloading data...")

    spy = yf.Ticker("SPY").history(start=START_DATE, end=END_DATE)
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
    print("  Running simulation...")
    trades, equity_curve = run_portfolio_sim(data, spy)
    print_portfolio_results(trades, equity_curve)
    input("Press Enter to close...")
