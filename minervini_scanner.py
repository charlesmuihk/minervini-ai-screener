import yfinance as yf
import pandas as pd
import numpy as np
import time, os, csv, math
from pathlib import Path
from datetime import datetime, date

WATCHLIST = [
    "NVDA","AAPL","MSFT","AMZN","GOOGL","META","AVGO","AMD","TSLA","ARM","PLTR","NFLX",
    "MU","MRVL","KLAC","LRCX","AMAT","ASML","MPWR","MCHP","NXPI","ONTO","ACLS","FORM",
    "CRWD","SNOW","DDOG","MDB","HUBS","APP","TTD","PANW","FTNT","ZS","NET","WDAY","ADSK",
    "NOW","ADBE","TWLO","AI","CLS","VRT","RKLB","DKNG","MSTR","UPST","FRPT","COIN",
    "V","MA","HOOD","SQ","PYPL","GS","MS","BAC","AXP","BLK","SCHW",
    "COST","BKNG","MELI","SHOP","UBER","ABNB","DUOL","ELF","CELH","WING","CVNA",
    "LLY","VRTX","REGN","ISRG","AMGN","TMO","DHR","SPOT","EA","COHR","LITE","AAOI","VIAV","CIEN",
    # Current AI infrastructure / momentum leaders that were missing from v2.0
    "ANET","PENG","ALAB","CRWV",
]

MIN_TREND = 6
MIN_EPS   = 0.20
MIN_REV   = 0.20
MIN_RS    = 70
MAX_DIST  = 0.35
STOP_PCT  = 0.08
VOL_MIN   = 0.8
PORTFOLIO_VALUE = 100_000
RISK_PER_TRADE_PCT = 1.0


def load_watchlist(path=None):
    """Load tickers from watchlist.csv when present; fallback to built-in WATCHLIST."""
    if path is None:
        path = Path(__file__).with_name("watchlist.csv")
    path = Path(path)
    tickers = []
    if path.exists():
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            sample = f.read(2048)
            f.seek(0)
            has_header = "ticker" in sample.splitlines()[0].lower() if sample.splitlines() else False
            if has_header:
                reader = csv.DictReader(f)
                for row in reader:
                    raw = (row.get("ticker") or row.get("Ticker") or "").strip()
                    if raw and not raw.startswith("#"):
                        tickers.append(raw.upper())
            else:
                for line in f:
                    raw = line.split(",")[0].strip()
                    if raw and not raw.startswith("#"):
                        tickers.append(raw.upper())
    else:
        tickers = list(WATCHLIST)
    deduped = []
    seen = set()
    for ticker in tickers:
        if ticker not in seen:
            deduped.append(ticker)
            seen.add(ticker)
    return deduped


def calc_rs_raw(sdf, mdf):
    try:
        n = min(len(sdf), len(mdf))
        if n < 126:
            return None
        def ret(df, days):
            if len(df) <= days:
                return None
            return df["Close"].iloc[-1] / df["Close"].iloc[-days] - 1
        periods = [(63, 0.4), (126, 0.3), (189, 0.2), (252, 0.1)]
        stock_score = 0
        market_score = 0
        used = 0
        for days, weight in periods:
            sr = ret(sdf, days)
            mr = ret(mdf, days)
            if sr is not None and mr is not None:
                stock_score += sr * weight
                market_score += mr * weight
                used += weight
        if used == 0:
            return None
        return (stock_score - market_score) / used
    except Exception:
        return None


def calc_rs_percentiles(scores):
    valid = {k: v for k, v in scores.items() if v is not None and not pd.isna(v)}
    if not valid:
        return {}
    ordered = sorted(valid.items(), key=lambda kv: kv[1])
    n = len(ordered)
    if n == 1:
        return {ordered[0][0]: 99}
    result = {}
    for idx, (ticker, _) in enumerate(ordered):
        result[ticker] = int(round(1 + idx * 98 / (n - 1)))
    return result


def classify_earnings_risk(next_earnings, today=None):
    if next_earnings is None or pd.isna(next_earnings):
        return "Unknown", None
    if today is None:
        today = date.today()
    if hasattr(next_earnings, "date"):
        next_earnings = next_earnings.date()
    days = (next_earnings - today).days
    if days < 0:
        return "Past", days
    if days <= 5:
        return "High", days
    if days <= 10:
        return "Medium", days
    if days <= 20:
        return "Watch", days
    return "Low", days


def get_next_earnings_date(ticker):
    try:
        tk = yf.Ticker(ticker)
        cal = tk.calendar
        if isinstance(cal, dict):
            dt = cal.get("Earnings Date") or cal.get("EarningsDate")
            if isinstance(dt, (list, tuple)):
                dt = dt[0]
            if dt is not None:
                return pd.to_datetime(dt).date()
        if hasattr(cal, "empty") and not cal.empty:
            vals = cal.values.flatten()
            if len(vals):
                return pd.to_datetime(vals[0]).date()
        info = getattr(tk, "info", {}) or {}
        ts = info.get("earningsTimestamp") or info.get("earningsTimestampStart")
        if ts:
            return datetime.fromtimestamp(ts).date()
    except Exception:
        pass
    return None


def calc_position_size(portfolio_value, risk_pct, entry_price, stop_price):
    if not entry_price or not stop_price or stop_price >= entry_price:
        return {"dollar_risk": round(portfolio_value * risk_pct / 100, 2), "stop_risk_pct": None, "position_value": 0, "shares": 0}
    dollar_risk = portfolio_value * risk_pct / 100
    stop_risk_pct = (entry_price - stop_price) / entry_price * 100
    risk_per_share = entry_price - stop_price
    shares = int(round(dollar_risk / risk_per_share)) if risk_per_share > 0 else 0
    position_value = shares * entry_price
    return {
        "dollar_risk": round(dollar_risk, 2),
        "stop_risk_pct": round(stop_risk_pct, 1),
        "position_value": round(position_value, 2),
        "shares": shares,
    }


def get_market_regime():
    try:
        spy = yf.Ticker("SPY").history(period="1y")["Close"]
        qqq = yf.Ticker("QQQ").history(period="3mo")["Close"]
        vix = yf.Ticker("^VIX").history(period="5d")["Close"]
        cp   = spy.iloc[-1]
        s50  = spy.rolling(50).mean().iloc[-1]
        s150 = spy.rolling(150).mean().iloc[-1]
        s200 = spy.rolling(200).mean().iloc[-1]
        s200_63 = spy.rolling(200).mean().iloc[-63]
        spy_score = sum([cp > s50, cp > s150, cp > s150 > s200])
        spy_pts = 2 if spy_score == 3 else (1 if spy_score >= 1 else 0)
        adv = yf.Ticker("^NYA").history(period="60d")["Close"]
        adv_score = 2 if adv.iloc[-1] > adv.rolling(50).mean().iloc[-1] else 0
        qqq_high = qqq.max()
        nh_score = 2 if qqq.iloc[-1] >= qqq_high * 0.97 else (1 if qqq.iloc[-1] >= qqq_high * 0.93 else 0)
        vix_val  = vix.iloc[-1]
        vix_score = 2 if vix_val < 20 else (1 if vix_val < 25 else 0)
        total = spy_pts + adv_score + nh_score + vix_score
        if total >= 7:
            regime, label = "BULL", "Full position sizing — aggressive entries OK"
        elif total >= 4:
            regime, label = "NEUTRAL", "Reduce size — selective entries only"
        else:
            regime, label = "BEAR", "Raise cash — avoid new longs"
        if regime == "BULL":
            pos_pct, max_pos = 100, "5-6 positions"
        elif regime == "NEUTRAL":
            pos_pct, max_pos = 50, "2-3 positions"
        else:
            pos_pct, max_pos = 0, "0 positions — cash only"
        return {"regime": regime, "label": label, "score": total,
                "spy": round(cp,2), "spy_pts": spy_pts,
                "adv_pts": adv_score, "nh_pts": nh_score,
                "vix": round(vix_val,1), "vix_pts": vix_score,
                "qqq_pct": round(qqq.iloc[-1]/qqq_high*100,1),
                "pos_pct": pos_pct, "max_pos": max_pos}
    except Exception as e:
        return {"regime": "UNKNOWN", "label": str(e), "score": 0,
                "spy": 0, "spy_pts": 0, "adv_pts": 0, "nh_pts": 0,
                "vix": 0, "vix_pts": 0, "qqq_pct": 0, "pos_pct": 50, "max_pos": "unknown"}

def calc_rs(sdf, mdf):
    try:
        n = min(len(sdf), len(mdf))
        if n < 200: return None
        def p(df, a, b): return df["Close"].iloc[b] / df["Close"].iloc[a] - 1
        ss = (0.2*p(sdf,-n,-int(n*.75)) + 0.2*p(sdf,-int(n*.75),-int(n*.5))
            + 0.3*p(sdf,-int(n*.5),-int(n*.25)) + 0.3*p(sdf,-int(n*.25),-1))
        ms = (0.2*p(mdf,-n,-int(n*.75)) + 0.2*p(mdf,-int(n*.75),-int(n*.5))
            + 0.3*p(mdf,-int(n*.5),-int(n*.25)) + 0.3*p(mdf,-int(n*.25),-1))
        return min(99, max(1, int(50 + (ss - ms) * 300)))
    except: return None

def check_trend(df):
    if len(df) < 252: return 0, []
    c    = df["Close"]
    cp   = c.iloc[-1]
    s50  = c.rolling(50).mean().iloc[-1]
    s150 = c.rolling(150).mean().iloc[-1]
    s200 = c.rolling(200).mean().iloc[-1]
    s200_63 = c.rolling(200).mean().iloc[-63]
    hi52 = c.rolling(252).max().iloc[-1]
    lo52 = c.rolling(252).min().iloc[-1]
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
    return sum(checks), checks

def calc_atr(df, period=14):
    try:
        high = df["High"]
        low = df["Low"]
        close = df["Close"]
        prev_close = close.shift(1)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ], axis=1).max(axis=1)
        return float(tr.rolling(period).mean().iloc[-1])
    except Exception:
        return None


def _find_swings(recent, n=3):
    highs, lows = [], []
    h = recent["High"].reset_index(drop=True)
    l = recent["Low"].reset_index(drop=True)
    c = recent["Close"].reset_index(drop=True)
    for i in range(n, len(recent) - n):
        if h.iloc[i] >= h.iloc[i-n:i+n+1].max():
            highs.append((i, float(h.iloc[i])))
        if l.iloc[i] <= l.iloc[i-n:i+n+1].min():
            lows.append((i, float(l.iloc[i])))
    if not highs:
        highs.append((int(c.idxmax()), float(c.max())))
    if not lows:
        lows.append((int(c.idxmin()), float(c.min())))
    return highs, lows


def detect_base_and_pivot(df, lookback=80):
    """Detect the current local base and actionable right-side pivot."""
    try:
        if len(df) < 40:
            return None
        recent = df.tail(min(lookback, len(df))).copy()
        close = recent["Close"]
        current = float(close.iloc[-1])
        base_high = float(recent["High"].max())
        base_low = float(recent["Low"].min())
        if base_high <= 0:
            return None
        base_depth_pct = (base_high - base_low) / base_high * 100

        # Right-side resistance shelf: recent highs before today's candle.
        shelf = recent.iloc[:-1].tail(20)
        if len(shelf) < 5:
            shelf = recent.iloc[:-1]
        pivot_price = float(shelf["High"].max()) if len(shelf) else base_high
        pivot_date_idx = shelf["High"].idxmax() if len(shelf) else recent["High"].idxmax()
        pivot_date = pivot_date_idx.strftime("%Y-%m-%d") if hasattr(pivot_date_idx, "strftime") else str(pivot_date_idx)[:10]
        distance_from_pivot_pct = (current / pivot_price - 1) * 100 if pivot_price else None

        avg20 = float(recent["Volume"].rolling(20).mean().iloc[-1]) if len(recent) >= 20 else float(recent["Volume"].mean())
        quiet_volume_ratio = float(recent["Volume"].tail(5).mean() / avg20) if avg20 > 0 else None
        atr = calc_atr(df)
        atr_pct = atr / current * 100 if atr and current else None
        raw_stop = float(recent["Low"].tail(15).min())
        # For active breakout/retest candidates, a stale low from the left side of the base
        # makes risk look unusably wide.  Use ~6% below the local pivot as the practical
        # invalidation floor, but never place the stop above current price.
        pivot_stop = pivot_price * 0.94 if current >= pivot_price * 0.92 else raw_stop
        stop_price = max(raw_stop, pivot_stop)
        if stop_price >= current:
            stop_price = raw_stop
        stop_risk_pct = (current - stop_price) / current * 100 if stop_price < current else None
        breakout_occurred = current >= pivot_price

        return {
            "base_high": round(base_high, 2),
            "base_low": round(base_low, 2),
            "base_depth_pct": round(base_depth_pct, 1),
            "base_length": len(recent),
            "pivot_price": round(pivot_price, 2),
            "pivot_date": pivot_date,
            "distance_from_pivot_pct": round(distance_from_pivot_pct, 1) if distance_from_pivot_pct is not None else None,
            "quiet_volume_ratio": round(quiet_volume_ratio, 2) if quiet_volume_ratio is not None else None,
            "atr_pct": round(atr_pct, 1) if atr_pct is not None else None,
            "stop_price": round(stop_price, 2),
            "stop_risk_pct": round(stop_risk_pct, 1) if stop_risk_pct is not None else None,
            "breakout_occurred": breakout_occurred,
        }
    except Exception:
        return None


def classify_setup_status(current_price, pivot_price, stop_price=None, breakout_occurred=False, quiet_volume_ratio=None):
    if not pivot_price:
        return "Leadership Candidate"
    dist = (current_price / pivot_price - 1) * 100
    stop_risk = (current_price - stop_price) / current_price * 100 if stop_price and stop_price < current_price else None
    quiet = quiet_volume_ratio is not None and quiet_volume_ratio <= 0.8
    risk_ok = stop_risk is None or stop_risk <= 8

    if dist > 8:
        return "Extended"
    if breakout_occurred and -3 <= dist <= 1 and quiet and risk_ok:
        return "Retest Watch"
    if 0 <= dist <= 5 and risk_ok:
        return "Actionable Pivot"
    if -3 <= dist < 0:
        return "Pivot Approaching"
    if -8 <= dist < -3:
        return "Setup Forming"
    if stop_risk is not None and stop_risk > 10:
        return "Base Repair"
    return "Leadership Candidate"


def detect_vcp_details(df):
    try:
        if len(df) < 60:
            return {"is_vcp": False, "score": 0, "pivot_price": None, "contractions": []}
        recent = df.tail(90).copy()
        highs, lows = _find_swings(recent, n=3)
        contractions = []
        reset = recent.reset_index(drop=True)
        for hi_idx, hi_price in highs:
            future_lows = [(li, lp) for li, lp in lows if li > hi_idx]
            if not future_lows:
                continue
            lo_idx, lo_price = future_lows[0]
            if hi_price > 0:
                contractions.append({
                    "hi_idx": hi_idx,
                    "lo_idx": lo_idx,
                    "high": round(float(hi_price), 2),
                    "low": round(float(lo_price), 2),
                    "depth_pct": round((hi_price - lo_price) / hi_price * 100, 1),
                })
        contractions = contractions[-4:]
        depths = [x["depth_pct"] for x in contractions]
        higher_lows = True
        if len(contractions) >= 2:
            low_prices = [float(reset["Low"].iloc[x["lo_idx"]]) for x in contractions]
            higher_lows = all(low_prices[i] >= low_prices[i-1] * 0.97 for i in range(1, len(low_prices)))
        progressively_shallower = len(depths) >= 2 and all(depths[i] <= depths[i-1] * 1.15 for i in range(1, len(depths)))
        final_tight = bool(depths and depths[-1] <= 10)
        base = detect_base_and_pivot(df, lookback=90)
        pivot_price = base["pivot_price"] if base else float(recent["High"].tail(20).max())
        dist = base["distance_from_pivot_pct"] if base else None
        near_pivot = dist is not None and -8 <= dist <= 8
        avg50 = float(recent["Volume"].rolling(50).mean().iloc[-1]) if len(recent) >= 50 else float(recent["Volume"].mean())
        final_vol = float(recent["Volume"].tail(5).mean())
        volume_dry = final_vol <= avg50 * 0.9 if avg50 > 0 else False

        score = 0
        if 2 <= len(contractions) <= 4: score += 2
        if progressively_shallower: score += 2
        if higher_lows: score += 1
        if final_tight: score += 1
        if volume_dry: score += 2
        if near_pivot: score += 2
        return {
            "is_vcp": score >= 6,
            "score": score,
            "pivot_price": round(float(pivot_price), 2) if pivot_price else None,
            "contractions": contractions,
            "contraction_count": len(contractions),
            "higher_lows": higher_lows,
            "progressively_shallower": progressively_shallower,
            "final_tight": final_tight,
            "volume_dry": volume_dry,
        }
    except Exception:
        return {"is_vcp": False, "score": 0, "pivot_price": None, "contractions": []}


def detect_vcp(df):
    details = detect_vcp_details(df)
    return details["is_vcp"], details["score"], details["pivot_price"]

def detect_cup_handle(df):
    try:
        if len(df) < 175: return False, None, None, None
        c = df["Close"].tail(175).reset_index(drop=True)
        cup_low_pos = int(c.idxmin())
        if cup_low_pos < 10 or cup_low_pos > len(c) - 15:
            return False, None, None, None
        left_high = c.iloc[:cup_low_pos].max()
        right_part = c.iloc[cup_low_pos:]
        right_high_pos = int(right_part.idxmax())
        right_high = c.iloc[right_high_pos]
        if right_high_pos >= len(c) - 5:
            return False, None, None, None
        base_high = max(left_high, right_high)
        cup_low = c.iloc[cup_low_pos]
        cup_depth = (base_high - cup_low) / base_high
        if not (0.12 <= cup_depth <= 0.35):
            return False, None, None, None
        handle = c.iloc[right_high_pos + 1:]
        if len(handle) < 5:
            return False, None, None, None
        handle_low = handle.min()
        handle_depth = (right_high - handle_low) / right_high
        if handle_depth > cup_depth * 0.60 or handle_depth > 0.15:
            return False, None, None, None
        pivot_price = round(float(min(left_high, handle.max())), 2)
        return True, pivot_price, round(cup_depth * 100, 1), round(handle_depth * 100, 1)
    except: return False, None, None, None

def detect_historical_pivot(df):
    try:
        if len(df) < 252: return None, None, None
        window = df["Close"].tail(252)
        low_idx = int(window.reset_index(drop=True).idxmin())
        low_price = float(window.iloc[low_idx])
        after = window.iloc[low_idx:]
        n = len(after)

        def _scan(threshold, start_i, end_i):
            for i in range(start_i, end_i - 1, -1):
                price = float(after.iloc[i])
                if price < low_price * 1.15:
                    continue
                w10 = after.iloc[i:i+10]
                avg10 = float(w10.mean())
                rng10 = float(w10.max() - w10.min())
                if avg10 > 0 and rng10 / avg10 <= threshold:
                    d = after.index[i]
                    pivot_date = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]
                    return round(price, 2), pivot_date
            return None, None

        recent_start = min(n - 11, max(n - 90 - 1, 0))

        # Layer 1: tight (8%) within most recent 90 trading days
        pp, pd = _scan(0.08, n - 11, recent_start)
        if pp is not None:
            return pp, pd, "tight_recent"

        # Layer 2: tight (8%) over full after sequence
        pp, pd = _scan(0.08, n - 11, 0)
        if pp is not None:
            return pp, pd, "tight_full"

        # Layer 3: loose (15%) over full after sequence
        pp, pd = _scan(0.15, n - 11, 0)
        if pp is not None:
            return pp, pd, "loose"

        # Fallback: most recent 3-day flat zone after 30% cumulative gain from low
        vals = list(after)
        idxs = list(after.index)
        gain_30_pos = next((i for i, v in enumerate(vals) if v >= low_price * 1.30), None)
        if gain_30_pos is not None:
            sv, si = vals[gain_30_pos:], idxs[gain_30_pos:]
            for i in range(len(sv) - 3, -1, -1):
                if (abs(sv[i+1]/sv[i] - 1) <= 0.02 and abs(sv[i+2]/sv[i+1] - 1) <= 0.02):
                    d = si[i]
                    pivot_date = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]
                    return round(max(sv[i], sv[i+1], sv[i+2]), 2), pivot_date, "fallback"

        return None, None, None
    except: return None, None, None

def get_fundamentals(ticker):
    try:
        info = yf.Ticker(ticker).info
        return (info.get("earningsQuarterlyGrowth"),
                info.get("revenueGrowth"),
                info.get("marketCap"),
                info.get("sector","N/A"))
    except: return None, None, None, "N/A"

def get_vol_ratio(df):
    try:
        avg50  = df["Volume"].rolling(50).mean().iloc[-1]
        recent = df["Volume"].tail(5).mean()
        return round(recent/avg50, 1) if avg50 > 0 else 0
    except: return 0

def scan():
    scan_date = datetime.now().strftime("%Y-%m-%d")
    tickers = load_watchlist()
    print("=" * 60)
    print(f"  Minervini Scanner v3.0 — {scan_date}")
    print("=" * 60)
    print("  Checking market regime...")
    rd = get_market_regime()
    print(f"  Market: {rd['regime']} (Score {rd['score']}/8)")
    print(f"  Position sizing: {rd['pos_pct']}% — {rd['max_pos']}")
    print()
    print("  Downloading SPY data...")
    spy_df = yf.Ticker("SPY").history(period="2y")
    print(f"  Downloading {len(tickers)} stock charts for RS percentile ranking...")
    data = {}
    raw_rs = {}
    for i, ticker in enumerate(tickers):
        try:
            df = yf.Ticker(ticker).history(period="2y")
            if len(df) >= 126:
                data[ticker] = df
                raw_rs[ticker] = calc_rs_raw(df, spy_df)
        except Exception:
            pass
        time.sleep(0.05)
    rs_rank = calc_rs_percentiles(raw_rs)

    print(f"  Scanning {len(tickers)} stocks...")
    results = []
    for i, ticker in enumerate(tickers):
        print(f"  [{i+1:02d}/{len(tickers)}] {ticker:<6}", end=" ", flush=True)
        try:
            df = data.get(ticker)
            if df is None or len(df) < 200:
                print("skip")
                continue
            trend_score, checks = check_trend(df)
            rs = rs_rank.get(ticker) or calc_rs(df, spy_df)
            eps, rev, mcap, sector = get_fundamentals(ticker)
            next_earnings = get_next_earnings_date(ticker)
            earnings_risk, days_to_earnings = classify_earnings_risk(next_earnings)
            vol_ratio = get_vol_ratio(df)
            base = detect_base_and_pivot(df)
            vcp_details = detect_vcp_details(df)
            is_vcp, vcp_score, vcp_pivot = vcp_details["is_vcp"], vcp_details["score"], vcp_details["pivot_price"]
            is_cup, cup_pivot, cup_depth_pct, handle_depth_pct = detect_cup_handle(df)
            hist_pivot_price, hist_pivot_date, hist_pivot_method = detect_historical_pivot(df)
            cp   = df["Close"].iloc[-1]
            hi52 = df["Close"].rolling(252).max().iloc[-1]
            dist = (cp/hi52 - 1) * 100
            if is_vcp and vcp_pivot is not None:
                pattern, pivot_price = "VCP", vcp_pivot
            elif is_cup and cup_pivot is not None:
                pattern, pivot_price = "CUP", cup_pivot
            elif base and base.get("pivot_price"):
                pattern, pivot_price = "BASE", base["pivot_price"]
            else:
                pattern, pivot_price = None, None
            pivot_dist = round((cp / pivot_price - 1) * 100, 1) if pivot_price else None
            hist_pivot_dist = round((cp / hist_pivot_price - 1) * 100, 1) if hist_pivot_price else None
            stop_price = base.get("stop_price") if base else round(cp * (1 - STOP_PCT), 2)
            setup_status = classify_setup_status(
                current_price=float(cp),
                pivot_price=pivot_price,
                stop_price=stop_price,
                breakout_occurred=bool(base.get("breakout_occurred")) if base else bool(pivot_price and cp >= pivot_price),
                quiet_volume_ratio=base.get("quiet_volume_ratio") if base else None,
            )
            pos = calc_position_size(PORTFOLIO_VALUE, RISK_PER_TRADE_PCT, float(cp), float(stop_price) if stop_price else None)
            # Allow Rev>30% to substitute missing EPS. Missing fundamentals no longer hide a valid technical setup.
            eps_ok = (eps or 0) >= MIN_EPS or (eps is None and (rev or 0) >= 0.30)
            fundamentals_ok = eps_ok and ((rev or 0) >= MIN_REV or rev is None)
            trend_rs_ok = trend_score >= MIN_TREND and (rs or 0) >= MIN_RS and dist >= -MAX_DIST * 100
            actionable_status = setup_status in {"Retest Watch", "Actionable Pivot", "Pivot Approaching", "Setup Forming"}
            earnings_ok = earnings_risk not in {"High"}
            passed = trend_rs_ok and earnings_ok and (fundamentals_ok or actionable_status)
            if passed:
                if setup_status in {"Retest Watch", "Actionable Pivot", "Pivot Approaching"} and (rs or 0) >= 90:
                    tier = "A"
                elif actionable_status or (dist >= -10 and (rs or 0) >= 80):
                    tier = "B"
                else:
                    tier = "C"
                results.append({
                    "ticker": ticker, "sector": sector,
                    "price": round(cp,2), "dist": round(dist,1),
                    "stop": round(stop_price, 2) if stop_price else round(cp * (1 - STOP_PCT), 2), "trend": trend_score,
                    "checks": checks, "rs": rs, "rs_raw": round(raw_rs.get(ticker), 4) if raw_rs.get(ticker) is not None else None,
                    "eps": eps, "rev": rev, "vol_ratio": vol_ratio,
                    "mcap": mcap, "is_vcp": is_vcp,
                    "vcp_score": vcp_score, "vcp_details": vcp_details, "tier": tier,
                    "add1": round(cp*1.10, 2),
                    "add2": round(cp*1.20, 2),
                    "max_pos": round(cp*1.10*0.9, 2),
                    "pattern": pattern,
                    "pivot_price": pivot_price,
                    "pivot_dist": pivot_dist,
                    "setup_status": setup_status,
                    "base_depth_pct": base.get("base_depth_pct") if base else None,
                    "quiet_volume_ratio": base.get("quiet_volume_ratio") if base else None,
                    "atr_pct": base.get("atr_pct") if base else None,
                    "stop_risk_pct": base.get("stop_risk_pct") if base else None,
                    "shares": pos.get("shares"),
                    "position_value": pos.get("position_value"),
                    "earnings_date": next_earnings.isoformat() if next_earnings else None,
                    "earnings_risk": earnings_risk,
                    "days_to_earnings": days_to_earnings,
                    "hist_pivot_price": hist_pivot_price,
                    "hist_pivot_date": hist_pivot_date,
                    "hist_pivot_dist": hist_pivot_dist,
                    "hist_pivot_method": hist_pivot_method,
                })
                vcp_tag = " [VCP]" if is_vcp else ""
                print(f"PASS RS={rs} Pivot={pivot_dist if pivot_dist is not None else 'N/A'}% {setup_status} Tier={tier}{vcp_tag}")
            else:
                print(f"fail (trend={trend_score}/8 rs={rs} dist={dist:+.1f}% pivot={pivot_dist} status={setup_status} ER={earnings_risk})")
        except Exception as e:
            print(f"error ({e})")
        time.sleep(0.15)
    results.sort(key=lambda x: (x["tier"], -int(x.get("rs") or 0), abs(x.get("pivot_dist") or 99)))
    return results, rd, scan_date

def build_html(results, rd, scan_date):
    def fmt_pct(v):
        if v is None: return "<span style='color:#aaa'>N/A</span>"
        pct = v * 100
        col = "#27a03a" if pct >= 30 else ("#f5a623" if pct >= 15 else "#aaa")
        return f"<span style='color:{col}'>{'+'if pct>0 else ''}{pct:.1f}%</span>"

    def fmt_mcap(v):
        if not v: return "N/A"
        if v >= 1e12: return f"${v/1e12:.1f}T"
        if v >= 1e9:  return f"${v/1e9:.0f}B"
        return f"${v/1e6:.0f}M"

    def fmt_pivot(r):
        if r.get("pattern") is None: return "<span style='color:#aaa'>—</span>"
        pat = r["pattern"]
        bg = "#7f5af0" if pat == "VCP" else "#4a90d9"
        badge = f"<span style='background:{bg};color:#fff;padding:2px 7px;border-radius:10px;font-size:11px'>{pat}</span>"
        pp = r.get("pivot_price")
        pd = r.get("pivot_dist")
        if pp is None: return badge
        if pd is not None and -1 <= pd <= 5:
            dist_col = "#27a03a"
        elif pd is not None and 5 < pd <= 15:
            dist_col = "#f5a623"
        else:
            dist_col = "#e24b4a"
        dist_str = f"<span style='color:{dist_col}'>({'+'if pd>=0 else ''}{pd:.1f}%)</span>" if pd is not None else ""
        return f"{badge}<br>${pp:,.2f} {dist_str}"

    def fmt_hist_pivot(r):
        pp = r.get("hist_pivot_price")
        if pp is None: return "<span style='color:#aaa'>—</span>"
        pd = r.get("hist_pivot_dist")
        method = r.get("hist_pivot_method")
        col = "#e24b4a" if (pd is None or pd > 100) else ("#f5a623" if pd > 50 else "#27a03a")
        dist_str = f"<span style='color:{col}'>({'+'if pd>=0 else ''}{pd:.1f}%)</span>" if pd is not None else ""
        method_map = {"tight_recent": "近期", "tight_full": "全年", "loose": "寬鬆", "fallback": "粗略"}
        method_tag = f"<span style='color:#999;font-size:10px'>{method_map.get(method, method)}</span>" if method else ""
        return f"${pp:,.2f} {dist_str} {method_tag}"

    def fmt_rs(v):
        if v is None: return "<span style='color:#aaa'>N/A</span>"
        col = "#27a03a" if v >= 90 else ("#f5a623" if v >= 70 else "#e24b4a")
        return f"<span style='background:{col};color:#fff;padding:2px 8px;border-radius:12px;font-size:12px'>{v}</span>"

    def trend_bar(score, checks):
        bars = ""
        for c in checks:
            col = "#27a03a" if c else "#e0e0e0"
            bars += f"<span style='display:inline-block;width:18px;height:14px;background:{col};border-radius:2px;margin:1px'></span>"
        return f"<div style='display:flex;align-items:center;gap:2px'>{bars}<span style='margin-left:4px;font-size:12px;color:#888'>{score}/8</span></div>"

    def fmt_vcp_details(r):
        d = r.get("vcp_details") or {}
        cons = d.get("contractions") or []
        depths = "/".join([f"{c.get('depth_pct')}%" for c in cons[-3:]]) or "—"
        return f"Score {r.get('vcp_score',0)}/10<br><span style='font-size:10px;color:#888'>C: {depths}</span>"

    def fmt_earnings(r):
        risk = r.get("earnings_risk") or "Unknown"
        color = {"High":"#e24b4a","Medium":"#f5a623","Watch":"#f5a623","Low":"#27a03a"}.get(risk, "#888")
        date_txt = r.get("earnings_date") or "N/A"
        days = r.get("days_to_earnings")
        day_txt = f"{days}d" if days is not None else ""
        return f"<span style='color:{color};font-weight:600'>{risk}</span><br><span style='font-size:10px;color:#888'>{date_txt} {day_txt}</span>"

    r_col = {"BULL":"#27a03a","NEUTRAL":"#f5a623","BEAR":"#e24b4a"}.get(rd["regime"],"#888")
    rows = ""
    for r in results:
        dist_col = "#27a03a" if r["dist"]>=-3 else ("#f5a623" if r["dist"]>=-10 else "#e24b4a")
        tier_col = {"A":"#27a03a","B":"#f5a623","C":"#e24b4a"}.get(r["tier"],"#888")
        vcp_badge = "<span style='background:#7f5af0;color:#fff;padding:2px 7px;border-radius:10px;font-size:11px;margin-left:4px'>VCP</span>" if r["is_vcp"] else ""
        rows += f"""<tr>
          <td style='position:sticky;left:0;background:#fff;z-index:1'><strong>{r['ticker']}</strong>{vcp_badge}<br><span style='font-size:11px;color:#888'>{r['sector']}</span></td>
          <td><span style='background:{tier_col};color:#fff;padding:2px 8px;border-radius:10px;font-size:12px'>Tier {r['tier']}</span></td>
          <td>${r['price']:,.2f}</td>
          <td style='color:{dist_col};font-weight:600'>{r['dist']:+.1f}%</td>
          <td>{trend_bar(r['trend'],r['checks'])}</td>
          <td>{fmt_rs(r['rs'])}</td>
          <td><strong>{r.get('setup_status','—')}</strong><br><span style='font-size:10px;color:#888'>Risk {r.get('stop_risk_pct','—')}%</span></td>
          <td>{fmt_vcp_details(r)}</td>
          <td>{fmt_earnings(r)}</td>
          <td>{r.get('shares','—')}<br><span style='font-size:10px;color:#888'>${r.get('position_value',0):,.0f}</span></td>
          <td>{fmt_pct(r['eps'])}</td>
          <td>{fmt_pct(r['rev'])}</td>
          <td style='color:#e24b4a;font-weight:600'>${r['stop']}</td>
          <td style='color:#7f5af0;font-weight:600'>${r.get('add1','N/A')}</td>
          <td style='color:#7f5af0;font-weight:600'>${r.get('add2','N/A')}</td>
          <td>{r['vol_ratio']}x</td>
          <td>{fmt_mcap(r['mcap'])}</td>
          <td style='font-size:11px;padding:6px 8px;white-space:normal'>{fmt_pivot(r)}</td>
          <td style='font-size:11px;padding:6px 8px;white-space:normal'>{fmt_hist_pivot(r)}</td>
        </tr>"""

    avg_rs = int(np.mean([r["rs"] for r in results if r["rs"]])) if results else 0
    near5  = sum(1 for r in results if r["dist"]>=-5)
    vcp_cnt= sum(1 for r in results if r["is_vcp"])
    tier_a = sum(1 for r in results if r["tier"]=="A")

    cands = [r for r in results if r.get("pattern") is not None]
    if not cands:
        candidates_html = "<div class='cands'><p class='cands-empty'>今日沒有股票形成近期可進場的整理型態（VCP/杯柄），建議觀察等待。</p></div>"
    else:
        cards = ""
        for r in cands:
            pat = r["pattern"]
            stripe = "#7f5af0" if pat == "VCP" else "#4a90d9"
            badge = f"<span style='background:{stripe};color:#fff;padding:2px 7px;border-radius:10px;font-size:11px'>{pat}</span>"
            pp = r.get("pivot_price")
            pd = r.get("pivot_dist")
            dist_col = "#27a03a" if (pd is not None and -1 <= pd <= 5) else ("#f5a623" if (pd is not None and 5 < pd <= 15) else "#e24b4a")
            dist_str = f"<span style='color:{dist_col};font-weight:600'>({'+'if pd>=0 else ''}{pd:.1f}%)</span>" if pd is not None else ""
            pp_str = f"${pp:,.2f}" if pp is not None else "—"
            cards += (
                f"<div style='background:#f0f9f0;border-radius:10px;padding:12px 16px;"
                f"box-shadow:0 1px 3px rgba(0,0,0,.1);border-left:4px solid {stripe};min-width:160px'>"
                f"<div style='font-size:16px;font-weight:700;margin-bottom:5px'>{r['ticker']} {badge}</div>"
                f"<div style='font-size:12px;color:#555;margin-bottom:2px'>現價 <strong>${r['price']:,.2f}</strong></div>"
                f"<div style='font-size:12px;color:#555'>Pivot <strong>{pp_str}</strong> {dist_str}</div>"
                f"</div>"
            )
        candidates_html = (
            "<div class='cands'>"
            "<div class='cands-title'>&#127919; 今日候選 &mdash; 近期形成整理區的股票</div>"
            f"<div style='display:flex;flex-wrap:wrap;gap:10px'>{cards}</div>"
            "</div>"
        )

    return avg_rs, near5, vcp_cnt, tier_a, rows, r_col, candidates_html

def save_report(results, rd, scan_date):
    avg_rs, near5, vcp_cnt, tier_a, rows, r_col, candidates_html = build_html(results, rd, scan_date)
    pos_label = f"{rd['pos_pct']}% allocated — {rd['max_pos']}"
    html = f"""<!DOCTYPE html>
<html lang="zh-TW"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Minervini v3.0 — {scan_date}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f5f5f7;color:#1d1d1f;font-size:14px}}
.hdr{{background:#1d1d1f;color:#fff;padding:22px 32px}}
.hdr h1{{font-size:22px;font-weight:600}}
.hdr p{{color:#aaa;font-size:13px;margin-top:3px}}
.rbar{{padding:14px 32px;display:flex;align-items:center;gap:16px;border-bottom:1px solid #e8e8e8;background:#fff;flex-wrap:wrap}}
.rbadge{{padding:5px 14px;border-radius:20px;font-weight:600;font-size:14px;color:#fff;background:{r_col}}}
.pbox{{background:#f0f9f0;border:1px solid #c3e6cb;border-radius:8px;padding:6px 14px;font-size:13px;color:#27a03a;font-weight:600}}
.inds{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;padding:14px 32px;background:#fff;border-bottom:1px solid #e8e8e8}}
.ind{{background:#f5f5f7;border-radius:8px;padding:10px 14px}}
.ind-l{{font-size:11px;color:#888;margin-bottom:2px}}
.ind-v{{font-size:20px;font-weight:600;color:#27a03a}}
.ind-s{{font-size:11px;color:#888}}
.mets{{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;padding:14px 32px}}
.met{{background:#fff;border-radius:10px;padding:13px 16px;box-shadow:0 1px 3px rgba(0,0,0,.07)}}
.met-l{{font-size:11px;color:#888;margin-bottom:4px}}
.met-v{{font-size:24px;font-weight:600}}
.cands{{padding:0 32px 14px}}
.cands-title{{font-size:14px;font-weight:600;color:#1d1d1f;margin-bottom:10px}}
.cands-empty{{background:#f5f5f7;border-radius:8px;padding:12px 16px;font-size:13px;color:#aaa}}
.v2note{{background:#fffbe6;border:1px solid #ffe58f;padding:10px 32px;font-size:12px;color:#856404}}
.flt{{padding:12px 32px;display:flex;gap:10px;flex-wrap:wrap;align-items:center}}
.flt label{{font-size:12px;color:#555}}
select,input[type=text]{{font-size:13px;padding:5px 10px;border:1px solid #ddd;border-radius:7px;background:#fff}}
button{{padding:5px 13px;border:1px solid #ddd;border-radius:7px;background:#fff;cursor:pointer}}
.tw{{padding:0 32px 32px;overflow-x:auto}}
table{{width:max-content;min-width:100%;border-collapse:collapse;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.07)}}
th{{background:#f5f5f7;text-align:left;padding:9px 12px;font-size:11px;color:#555;font-weight:600;border-bottom:1px solid #e8e8e8;white-space:nowrap}}
td{{padding:9px 12px;border-bottom:1px solid #f2f2f2;vertical-align:middle}}
tr:hover td{{background:#fafafa}}
.ft{{padding:12px 32px;color:#aaa;font-size:11px;text-align:center}}
</style></head><body>
<div class="hdr">
  <h1>&#9889; Minervini Scanner &#8212; USIC 2026 <span style="font-size:14px;background:#7f5af0;color:#fff;padding:2px 10px;border-radius:12px;margin-left:8px">v3.0</span></h1>
  <p>Date: {scan_date} | Scanned: {len(load_watchlist())} | Passed: {len(results)} | RS percentile | Risk/trade: {RISK_PER_TRADE_PCT}%</p>
</div>
<div class="rbar">
  <span class="rbadge">{rd['regime']}</span>
  <span style="font-size:13px;color:#555;flex:1">{rd['label']}</span>
  <span class="pbox">Position sizing: {pos_label}</span>
  <span style="font-size:13px;color:#888">Score: {rd['score']}/8</span>
</div>
<div class="inds">
  <div class="ind"><div class="ind-l">SPY trend</div><div class="ind-v">{rd['spy_pts']}/2</div><div class="ind-s">${rd['spy']}</div></div>
  <div class="ind"><div class="ind-l">Advance/Decline</div><div class="ind-v">{rd['adv_pts']}/2</div><div class="ind-s">Breadth</div></div>
  <div class="ind"><div class="ind-l">New High/Low</div><div class="ind-v">{rd['nh_pts']}/2</div><div class="ind-s">QQQ {rd['qqq_pct']}% of high</div></div>
  <div class="ind"><div class="ind-l">VIX</div><div class="ind-v">{rd['vix_pts']}/2</div><div class="ind-s">{rd['vix']}</div></div>
</div>
<div class="mets">
  <div class="met"><div class="met-l">Passed</div><div class="met-v">{len(results)}</div></div>
  <div class="met"><div class="met-l">Avg RS</div><div class="met-v">{avg_rs}</div></div>
  <div class="met"><div class="met-l">Within 5% of high</div><div class="met-v">{near5}</div></div>
  <div class="met"><div class="met-l">VCP patterns</div><div class="met-v" style="color:#7f5af0">{vcp_cnt}</div></div>
  <div class="met"><div class="met-l">Tier A setups</div><div class="met-v" style="color:#27a03a">{tier_a}</div></div>
</div>
{candidates_html}
<div class="v2note">&#9888; v3.0: External watchlist · RS percentile · Local pivot distance · Setup status · VCP contraction depths · Earnings risk · Position sizing</div>
<div class="flt">
  <label>Search: <input type="text" id="sb" placeholder="ticker..." oninput="ft()"></label>
  <label>Tier: <select id="ts" onchange="ft()"><option value="">All</option><option>A</option><option>B</option><option>C</option></select></label>
  <label>VCP only: <input type="checkbox" id="vc" onchange="ft()"></label>
  <button onclick="document.getElementById('sb').value='';document.getElementById('ts').value='';document.getElementById('vc').checked=false;ft()">Reset</button>
</div>
<div class="tw"><table>
  <thead><tr>
    <th style="position:sticky;left:0;background:#f5f5f7;z-index:2">Ticker</th><th>Tier</th><th>Price</th><th>From High</th><th>Trend Score</th><th>RS</th><th>Setup</th><th>VCP</th><th>Earnings</th><th>Size</th><th>EPS</th><th>Revenue</th><th>Stop Loss</th><th style="color:#7f5af0">Add 1 +10%</th><th style="color:#7f5af0">Add 2 +20%</th><th>Vol Ratio</th><th>Mkt Cap</th><th style="white-space:normal;min-width:90px;padding:9px 8px">Pivot</th><th style="white-space:normal;min-width:110px;padding:9px 8px">歷史Pivot</th>
  </tr></thead>
  <tbody id="tb">{rows}</tbody>
</table></div>
<div class="ft">Research only | Minervini Scanner v3.0 | {scan_date}</div>
<script>
function ft(){{
  var q=document.getElementById('sb').value.toLowerCase();
  var ts=document.getElementById('ts').value;
  var vc=document.getElementById('vc').checked;
  document.querySelectorAll('#tb tr').forEach(function(tr){{
    var txt=tr.innerText.toLowerCase();
    var tok=!ts||txt.includes('tier '+ts.toLowerCase());
    var vok=!vc||txt.includes('vcp');
    tr.style.display=(txt.includes(q)&&tok&&vok)?'':'none';
  }});
}}
</script>
</body></html>"""
    fname = f"minervini_{scan_date}.html"
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
    os.makedirs(out_dir, exist_ok=True)
    fpath = os.path.join(out_dir, fname)
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(html)
    return fpath

if __name__ == "__main__":
    results, rd, scan_date = scan()
    fpath = save_report(results, rd, scan_date)
    abs_path = os.path.abspath(fpath)
    wp = abs_path.replace("/home/wahmui", "").replace("/", "\\")
    win_path = "\\\\wsl.localhost\\Ubuntu\\home\\wahmui" + wp
    print("=" * 60)
    print(f"  {len(results)} stocks passed (v3.0 filters)")
    tier_a = [r for r in results if r["tier"]=="A"]
    tier_b = [r for r in results if r["tier"]=="B"]
    tier_c = [r for r in results if r["tier"]=="C"]
    if tier_a:
        print("  TIER A:")
        for r in tier_a:
            vcp = " [VCP]" if r["is_vcp"] else ""
            print(f"    {r['ticker']:<6} RS={str(r['rs'] or 'N/A'):>3} Dist={r['dist']:+.1f}% Stop=${r['stop']}{vcp}")
    if tier_b:
        print("  TIER B:")
        for r in tier_b:
            print(f"    {r['ticker']:<6} RS={str(r['rs'] or 'N/A'):>3} Dist={r['dist']:+.1f}% Stop=${r['stop']}")
    if tier_c:
        print("  TIER C:")
        for r in tier_c:
            print(f"    {r['ticker']:<6} RS={str(r['rs'] or 'N/A'):>3} Dist={r['dist']:+.1f}% Stop=${r['stop']}")
    print("=" * 60)
    import subprocess, shutil

    def open_report_on_windows(report_path):
        """When running inside WSL, copy report to Windows Desktop and open it."""
        try:
            if shutil.which("powershell.exe") is None:
                return False
            report_name = os.path.basename(report_path)
            desktop_win = subprocess.check_output(
                ["powershell.exe", "-NoProfile", "-Command", "[Environment]::GetFolderPath('Desktop')"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            if not desktop_win:
                return False
            desktop_wsl = subprocess.check_output(["wslpath", "-u", desktop_win], text=True).strip()
            if os.path.isdir(desktop_wsl):
                desktop_report = os.path.join(desktop_wsl, report_name)
                shutil.copy(report_path, desktop_report)
                subprocess.Popen(["powershell.exe", "-NoProfile", "-Command", f"Start-Process -FilePath '{desktop_win}\\{report_name}'"])
                print(f"Scan complete! Browser opening: {desktop_win}\\{report_name}")
                return True
        except Exception:
            return False
        return False

    if not open_report_on_windows(fpath):
        print(f"Scan complete! Report saved to {fpath}")
