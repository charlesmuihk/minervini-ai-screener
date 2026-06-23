import os, sys

path = os.path.expanduser("~/minervini-ai-screener/minervini_scanner.py")

part1 = '''import yfinance as yf
import pandas as pd
import numpy as np
import time, os
from datetime import datetime

WATCHLIST = [
    "NVDA","AAPL","MSFT","AMZN","GOOGL","META","AVGO","AMD","TSLA","ARM","PLTR","NFLX",
    "MU","MRVL","KLAC","LRCX","AMAT","ASML","MPWR","MCHP","NXPI","ONTO","ACLS","FORM",
    "CRWD","SNOW","DDOG","MDB","HUBS","APP","TTD","PANW","FTNT","ZS","NET","WDAY","ADSK",
    "NOW","ADBE","TWLO","AI","CLS","VRT","RKLB","DKNG","MSTR","UPST","FRPT","COIN",
    "V","MA","HOOD","SQ","PYPL","GS","MS","BAC","AXP","BLK","SCHW",
    "COST","BKNG","MELI","SHOP","UBER","ABNB","DUOL","ELF","CELH","WING","CVNA",
    "LLY","VRTX","REGN","ISRG","AMGN","TMO","DHR","SPOT","EA",
]

MIN_TREND = 6
MIN_EPS   = 0.20
MIN_REV   = 0.20
MIN_RS    = 70
MAX_DIST  = 0.35
STOP_PCT  = 0.08
VOL_MIN   = 1.5
'''

with open(path, "w") as f:
    f.write(part1)
print("Part 1 OK")

part2 = '''
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
'''

with open(path, "a") as f:
    f.write(part2)
print("Part 2 OK")

part3 = '''
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

def detect_vcp(df):
    try:
        if len(df) < 60: return False, 0
        recent = df.tail(30)
        c = recent["Close"]
        v = recent["Volume"]
        seg     = [c.iloc[i*10:(i+1)*10] for i in range(3)]
        vol_seg = [v.iloc[i*10:(i+1)*10] for i in range(3)]
        pullbacks = [(s.max()-s.min())/s.max() for s in seg]
        vol_trend = [vs.mean() for vs in vol_seg]
        contracting = pullbacks[0] > pullbacks[1] > pullbacks[2]
        vol_drying  = vol_trend[0] > vol_trend[1] > vol_trend[2]
        tight_range = pullbacks[2] < 0.05
        near_high   = c.iloc[-1] >= c.max() * 0.97
        vcp_score = sum([contracting, vol_drying, tight_range, near_high])
        return vcp_score >= 3, vcp_score
    except: return False, 0

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
'''

with open(path, "a") as f:
    f.write(part3)
print("Part 3 OK")

part4 = '''
def scan():
    scan_date = datetime.now().strftime("%Y-%m-%d")
    print("=" * 60)
    print(f"  Minervini Scanner v2.0 — {scan_date}")
    print("=" * 60)
    print("  Checking market regime...")
    rd = get_market_regime()
    print(f"  Market: {rd['regime']} (Score {rd['score']}/8)")
    print(f"  Position sizing: {rd['pos_pct']}% — {rd['max_pos']}")
    print()
    print("  Downloading SPY data...")
    spy_df = yf.Ticker("SPY").history(period="2y")
    print(f"  Scanning {len(WATCHLIST)} stocks...\n")
    results = []
    for i, ticker in enumerate(WATCHLIST):
        print(f"  [{i+1:02d}/{len(WATCHLIST)}] {ticker:<6}", end=" ", flush=True)
        try:
            df = yf.Ticker(ticker).history(period="2y")
            if len(df) < 200:
                print("skip")
                continue
            trend_score, checks = check_trend(df)
            rs = calc_rs(df, spy_df)
            eps, rev, mcap, sector = get_fundamentals(ticker)
            vol_ratio = get_vol_ratio(df)
            is_vcp, vcp_score = detect_vcp(df)
            cp   = df["Close"].iloc[-1]
            hi52 = df["Close"].rolling(252).max().iloc[-1]
            dist = (cp/hi52 - 1) * 100
            stop_price = round(cp * (1 - STOP_PCT), 2)
            passed = (
                trend_score >= MIN_TREND and
                (rs or 0) >= MIN_RS and
                (eps or 0) >= MIN_EPS and
                (rev or 0) >= MIN_REV and
                dist >= -MAX_DIST * 100 and
                vol_ratio >= VOL_MIN
            )
            if passed:
                if is_vcp and dist >= -5:
                    tier = "A"
                elif dist >= -5 and (rs or 0) >= 90:
                    tier = "A"
                elif dist >= -10:
                    tier = "B"
                else:
                    tier = "C"
                results.append({
                    "ticker": ticker, "sector": sector,
                    "price": round(cp,2), "dist": round(dist,1),
                    "stop": stop_price, "trend": trend_score,
                    "checks": checks, "rs": rs, "eps": eps,
                    "rev": rev, "vol_ratio": vol_ratio,
                    "mcap": mcap, "is_vcp": is_vcp,
                    "vcp_score": vcp_score, "tier": tier,
                })
                vcp_tag = " [VCP]" if is_vcp else ""
                print(f"PASS RS={rs} Dist={dist:+.1f}% Tier={tier}{vcp_tag}")
            else:
                print(f"fail (trend={trend_score}/8 rs={rs} dist={dist:+.1f}% vol={vol_ratio}x)")
        except Exception as e:
            print(f"error ({e})")
        time.sleep(0.3)
    results.sort(key=lambda x: (x["tier"], -x["dist"]))
    return results, rd, scan_date
'''

with open(path, "a") as f:
    f.write(part4)
print("Part 4 OK")

part5 = '''
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

    r_col = {"BULL":"#27a03a","NEUTRAL":"#f5a623","BEAR":"#e24b4a"}.get(rd["regime"],"#888")
    rows = ""
    for r in results:
        dist_col = "#27a03a" if r["dist"]>=-3 else ("#f5a623" if r["dist"]>=-10 else "#e24b4a")
        tier_col = {"A":"#27a03a","B":"#f5a623","C":"#e24b4a"}.get(r["tier"],"#888")
        vcp_badge = "<span style='background:#7f5af0;color:#fff;padding:2px 7px;border-radius:10px;font-size:11px;margin-left:4px'>VCP</span>" if r["is_vcp"] else ""
        rows += f"""<tr>
          <td><strong>{r['ticker']}</strong>{vcp_badge}<br><span style='font-size:11px;color:#888'>{r['sector']}</span></td>
          <td><span style='background:{tier_col};color:#fff;padding:2px 8px;border-radius:10px;font-size:12px'>Tier {r['tier']}</span></td>
          <td>${r['price']:,.2f}</td>
          <td style='color:{dist_col};font-weight:600'>{r['dist']:+.1f}%</td>
          <td style='color:#e24b4a;font-weight:600'>${r['stop']}</td>
          <td>{trend_bar(r['trend'],r['checks'])}</td>
          <td>{fmt_rs(r['rs'])}</td>
          <td>{fmt_pct(r['eps'])}</td>
          <td>{fmt_pct(r['rev'])}</td>
          <td>{r['vol_ratio']}x</td>
          <td>{fmt_mcap(r['mcap'])}</td>
        </tr>"""

    avg_rs = int(np.mean([r["rs"] for r in results if r["rs"]])) if results else 0
    near5  = sum(1 for r in results if r["dist"]>=-5)
    vcp_cnt= sum(1 for r in results if r["is_vcp"])
    tier_a = sum(1 for r in results if r["tier"]=="A")
    return avg_rs, near5, vcp_cnt, tier_a, rows, r_col
'''

with open(path, "a") as f:
    f.write(part5)
print("Part 5 OK")

part6 = '''
def save_report(results, rd, scan_date):
    avg_rs, near5, vcp_cnt, tier_a, rows, r_col = build_html(results, rd, scan_date)
    pos_label = f"{rd['pos_pct']}% allocated — {rd['max_pos']}"
    html = f"""<!DOCTYPE html>
<html lang="zh-TW"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Minervini v2.0 — {scan_date}</title>
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
.v2note{{background:#fffbe6;border:1px solid #ffe58f;padding:10px 32px;font-size:12px;color:#856404}}
.flt{{padding:12px 32px;display:flex;gap:10px;flex-wrap:wrap;align-items:center}}
.flt label{{font-size:12px;color:#555}}
select,input[type=text]{{font-size:13px;padding:5px 10px;border:1px solid #ddd;border-radius:7px;background:#fff}}
button{{padding:5px 13px;border:1px solid #ddd;border-radius:7px;background:#fff;cursor:pointer}}
.tw{{padding:0 32px 32px;overflow-x:auto}}
table{{width:100%;border-collapse:collapse;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.07)}}
th{{background:#f5f5f7;text-align:left;padding:9px 12px;font-size:11px;color:#555;font-weight:600;border-bottom:1px solid #e8e8e8;white-space:nowrap}}
td{{padding:9px 12px;border-bottom:1px solid #f2f2f2;vertical-align:middle}}
tr:hover td{{background:#fafafa}}
.ft{{padding:12px 32px;color:#aaa;font-size:11px;text-align:center}}
</style></head><body>
<div class="hdr">
  <h1>&#9889; Minervini Scanner &#8212; USIC 2026 <span style="font-size:14px;background:#7f5af0;color:#fff;padding:2px 10px;border-radius:12px;margin-left:8px">v2.0</span></h1>
  <p>Date: {scan_date} | Scanned: {len(WATCHLIST)} | Passed: {len(results)} | Vol filter: &ge;{VOL_MIN}x | Stop: {int(STOP_PCT*100)}%</p>
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
<div class="v2note">&#9888; v2.0: Volume &ge;{VOL_MIN}x · 8% stop loss · Dynamic position sizing · VCP detection · Tiers A/B/C</div>
<div class="flt">
  <label>Search: <input type="text" id="sb" placeholder="ticker..." oninput="ft()"></label>
  <label>Tier: <select id="ts" onchange="ft()"><option value="">All</option><option>A</option><option>B</option><option>C</option></select></label>
  <label>VCP only: <input type="checkbox" id="vc" onchange="ft()"></label>
  <button onclick="document.getElementById('sb').value='';document.getElementById('ts').value='';document.getElementById('vc').checked=false;ft()">Reset</button>
</div>
<div class="tw"><table>
  <thead><tr>
    <th>Ticker</th><th>Tier</th><th>Price</th><th>From High</th>
    <th>Stop Loss</th><th>Trend Score</th><th>RS</th>
    <th>EPS</th><th>Revenue</th><th>Vol Ratio</th><th>Mkt Cap</th>
  </tr></thead>
  <tbody id="tb">{rows}</tbody>
</table></div>
<div class="ft">Research only | Minervini Scanner v2.0 | {scan_date}</div>
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
    fpath = os.path.expanduser(f"~/minervini-ai-screener/{fname}")
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(html)
    return fpath
'''

with open(path, "a") as f:
    f.write(part6)
print("Part 6 OK")


part7 = '''
if __name__ == "__main__":
    results, rd, scan_date = scan()
    fpath = save_report(results, rd, scan_date)
    abs_path = os.path.abspath(fpath)
    wp = abs_path.replace("/home/wahmui", "").replace("/", "\\\\")
    win_path = "\\\\\\\\wsl.localhost\\\\Ubuntu\\\\home\\\\wahmui" + wp
    print("=" * 60)
    print(f"  {len(results)} stocks passed (v2.0 filters)")
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
    import subprocess
    subprocess.Popen(["cmd.exe", "/c", "start", win_path])
    input("Press Enter to close...")
'''

with open(path, "a") as f:
    f.write(part7)
print("Part 7 OK — installation complete!")
