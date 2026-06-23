import yfinance as yf
import pandas as pd
import numpy as np
import time, os
from datetime import datetime

WATCHLIST = [
    "NVDA","AAPL","MSFT","AMZN","GOOGL","META","AVGO","AMD","TSLA","ARM","PLTR","NFLX",
    "MU","MRVL","KLAC","LRCX","AMAT","ASML","MPWR","MCHP","NXPI","ONTO","ACLS","FORM",
    "CRWD","SNOW","DDOG","MDB","HUBS","APP","TTD","PANW","FTNT","ZS","NET","WDAY","ADSK","NOW","ADBE","TWLO","AI",
    "V","MA","COIN","HOOD","SQ","PYPL","GS","MS","BAC","AXP","BLK","SCHW",
    "COST","BKNG","MELI","SHOP","UBER","ABNB","RBLX","DUOL","ELF","CELH","WING","CVNA",
    "LLY","VRTX","REGN","ISRG","AMGN","TMO","DHR",
    "RKLB","VRT","CLS","SPOT","EA","DKNG","MSTR","UPST","FRPT",
]

MIN_TREND = 6
MIN_EPS   = 0.20
MIN_REV   = 0.20
MIN_RS    = 70
MAX_DIST  = 0.35

def get_market_regime():
    try:
        spy = yf.Ticker("SPY").history(period="1y")["Close"]
        cp    = spy.iloc[-1]
        s50   = spy.rolling(50).mean().iloc[-1]
        s150  = spy.rolling(150).mean().iloc[-1]
        s200  = spy.rolling(200).mean().iloc[-1]
        s200b = spy.rolling(200).mean().iloc[-20]
        spy_score = sum([cp>s50, cp>s150, cp>s200, s150>s200, s200>s200b])
        spy_pts = 2 if spy_score==5 else (1 if spy_score>=3 else 0)
        sample = ["NVDA","AAPL","MSFT","AMZN","GOOGL","META","AMD","TSLA","AVGO","PLTR",
                  "CRWD","DDOG","NOW","PANW","MRVL","MU","LRCX","AMAT","LLY","V",
                  "MA","COST","NFLX","ADBE","INTU","ISRG","AMGN","TXN","QCOM","FTNT"]
        above = 0
        for t in sample:
            try:
                c = yf.Ticker(t).history(period="200d")["Close"]
                if len(c) > 50 and c.iloc[-1] > c.rolling(50).mean().iloc[-1]:
                    above += 1
            except:
                pass
        ad_pct = above / len(sample) * 100
        ad_pts = 2 if ad_pct >= 60 else (1 if ad_pct >= 40 else 0)
        qqq = yf.Ticker("QQQ").history(period="1y")["Close"]
        iwm = yf.Ticker("IWM").history(period="1y")["Close"]
        qqq_hi = float(qqq.iloc[-1] / qqq.max())
        iwm_hi = float(iwm.iloc[-1] / iwm.max())
        hl_score = (qqq_hi + iwm_hi) / 2
        hl_pts = 2 if hl_score >= 0.90 else (1 if hl_score >= 0.75 else 0)
        vix = float(yf.Ticker("^VIX").history(period="5d")["Close"].iloc[-1])
        vix_pts = 2 if vix < 20 else (1 if vix < 30 else 0)
        total = spy_pts + ad_pts + hl_pts + vix_pts
        if total >= 6:
            label = "BULL"
            color = "#27a03a"
            bg    = "#e6f4ea"
            action = "Full position sizing — aggressive entries OK"
        elif total >= 3:
            label = "NEUTRAL"
            color = "#e07b00"
            bg    = "#fff3cd"
            action = "Half position sizing — selective entries only"
        else:
            label = "BEAR"
            color = "#d0342c"
            bg    = "#fce8e8"
            action = "Cash only — no new longs"
        return {
            "label": label, "color": color, "bg": bg,
            "action": action, "total": total,
            "spy_pts": spy_pts, "ad_pts": ad_pts,
            "hl_pts": hl_pts, "vix_pts": vix_pts,
            "spy_price": round(float(cp), 2),
            "ad_pct": round(ad_pct, 0),
            "vix": round(vix, 1),
            "qqq_hi": round(qqq_hi * 100, 1),
            "iwm_hi": round(iwm_hi * 100, 1),
        }
    except Exception as e:
        return {
            "label": "UNKNOWN", "color": "#888", "bg": "#f5f5f5",
            "action": "Could not calculate", "total": 0,
            "spy_pts": 0, "ad_pts": 0, "hl_pts": 0, "vix_pts": 0,
            "spy_price": 0, "ad_pct": 0, "vix": 0, "qqq_hi": 0, "iwm_hi": 0,
        }

def calc_rs(sdf, mdf):
    try:
        n = min(len(sdf), len(mdf))
        if n < 200: return None
        def p(df, a, b): return df["Close"].iloc[b] / df["Close"].iloc[a] - 1
        ss = 0.2*p(sdf,-n,-int(n*.75)) + 0.2*p(sdf,-int(n*.75),-int(n*.5)) + 0.3*p(sdf,-int(n*.5),-int(n*.25)) + 0.3*p(sdf,-int(n*.25),-1)
        ms = 0.2*p(mdf,-n,-int(n*.75)) + 0.2*p(mdf,-int(n*.75),-int(n*.5)) + 0.3*p(mdf,-int(n*.5),-int(n*.25)) + 0.3*p(mdf,-int(n*.25),-1)
        return min(99, max(1, int(50 + (ss - ms) * 200)))
    except:
        return None

def analyze(ticker, spy):
    try:
        tk = yf.Ticker(ticker)
        info = tk.info
        df = tk.history(period="1y")
        if len(df) < 200: return None
        c = df["Close"]
        v = df["Volume"]
        cp = c.iloc[-1]
        s50  = c.rolling(50).mean().iloc[-1]
        s150 = c.rolling(150).mean().iloc[-1]
        s200 = c.rolling(200).mean().iloc[-1]
        s200b = c.rolling(200).mean().iloc[-20]
        lo = c.min()
        hi = c.max()
        conds = {
            "C1 Price>SMA50":   cp > s50,
            "C2 Price>SMA150":  cp > s150,
            "C3 Price>SMA200":  cp > s200,
            "C4 SMA150>SMA200": s150 > s200,
            "C5 SMA200 rising": s200 > s200b,
            "C6 SMA50>SMA150":  s50 > s150,
            "C7 +30% from low": cp >= lo * 1.30,
            "C8 <35% from high":cp >= hi * 0.75,
        }
        av = v.rolling(50).mean().iloc[-1]
        vr = round(v.iloc[-5:].mean() / av, 2) if av > 0 else None
        return {
            "ticker": ticker,
            "name":   info.get("shortName", ticker),
            "sector": info.get("sector", "N/A"),
            "price":  round(cp, 2),
            "hi":     round(hi, 2),
            "lo":     round(lo, 2),
            "dist":   round((cp - hi) / hi * 100, 2),
            "score":  sum(conds.values()),
            "conds":  conds,
            "vr":     vr,
            "rs":     calc_rs(df, spy),
            "eps":    info.get("earningsGrowth") or info.get("earningsQuarterlyGrowth"),
            "rev":    info.get("revenueGrowth"),
            "mcap":   info.get("marketCap"),
        }
    except:
        return None

def pct(v):
    if v is None: return "N/A"
    return ("+" if v >= 0 else "") + str(round(v * 100, 1)) + "%"

def mcap(v):
    if not v: return "N/A"
    if v >= 1e12: return "$" + str(round(v/1e12, 1)) + "T"
    if v >= 1e9:  return "$" + str(round(v/1e9)) + "B"
    return "$" + str(round(v/1e6)) + "M"

def badge(v, t0, t1, txt):
    if v is None: return "<span style='color:#bbb'>N/A</span>"
    if v >= t0:
        bg, fg = "#e6f4ea", "#1e7e34"
    elif v >= t1:
        bg, fg = "#fff3cd", "#856404"
    else:
        bg, fg = "#fce8e8", "#b01c1c"
    return "<span style='background:" + bg + ";color:" + fg + ";padding:2px 9px;border-radius:99px;font-size:12px;font-weight:500'>" + txt + "</span>"

def dist_cell(v):
    if v >= -5:   col = "#27a03a"
    elif v >= -15: col = "#e07b00"
    else:          col = "#d0342c"
    w = max(0, min(100, int((1 - abs(v)/35)*100)))
    return "<div style='display:flex;align-items:center;gap:6px'><span style='color:" + col + ";font-weight:600;min-width:46px'>" + str(round(v,1)) + "%</span><div style='background:#e8e8e8;border-radius:3px;height:5px;width:56px;overflow:hidden'><div style='background:" + col + ";height:100%;width:" + str(w) + "%'></div></div></div>"

def score_cell(s):
    if s >= 7:   col = "#27a03a"
    elif s >= 5: col = "#e07b00"
    else:        col = "#d0342c"
    filled = "&#9646;" * s
    empty  = "&#9647;" * (8 - s)
    return "<span style='color:" + col + ";letter-spacing:2px'>" + filled + empty + "</span> <span style='color:#888;font-size:12px'>" + str(s) + "/8</span>"

def make_html(res, date, total, regime):
    rows = ""
    for r in res:
        ch = ""
        for k, ok in r["conds"].items():
            color = "#27a03a" if ok else "#d0342c"
            mark  = "&#10003;" if ok else "&#10007;"
            ch += "<span style='color:" + color + ";font-size:11px' title='" + k + "'>" + mark + " </span>"
        vr_str = (str(round(r["vr"], 1)) + "x") if r["vr"] else "N/A"
        rs_badge  = badge(r["rs"],  80,  60, str(r["rs"]) if r["rs"] else "N/A")
        eps_badge = badge(r["eps"], 0.5, 0.2, pct(r["eps"]))
        rev_badge = badge(r["rev"], 0.3, 0.1, pct(r["rev"]))
        rows += "<tr>"
        rows += "<td><b>" + r["ticker"] + "</b><br><span style='font-size:11px;color:#888'>" + r["name"][:22] + "</span></td>"
        rows += "<td><span style='background:#f0f0f5;color:#555;font-size:11px;padding:2px 7px;border-radius:5px'>" + (r["sector"] or "N/A")[:15] + "</span></td>"
        rows += "<td>$" + str(r["price"]) + "</td>"
        rows += "<td>" + dist_cell(r["dist"]) + "</td>"
        rows += "<td>" + score_cell(r["score"]) + "<br><span style='font-size:10px'>" + ch + "</span></td>"
        rows += "<td>" + rs_badge + "</td>"
        rows += "<td>" + eps_badge + "</td>"
        rows += "<td>" + rev_badge + "</td>"
        rows += "<td style='font-size:13px'>" + vr_str + "</td>"
        rows += "<td style='font-size:13px'>" + mcap(r["mcap"]) + "</td>"
        rows += "</tr>"

    rs_v   = [r["rs"]  for r in res if r["rs"]]
    ep_v   = [r["eps"] for r in res if r["eps"] is not None]
    avg_rs = int(np.mean(rs_v)) if rs_v else 0
    avg_ep = round(np.mean(ep_v) * 100) if ep_v else 0
    near5  = sum(1 for r in res if abs(r["dist"]) <= 5)

    regime_html = (
        "<div style='margin:16px 30px;padding:16px 20px;background:" + regime["bg"] + ";border-radius:12px;border-left:5px solid " + regime["color"] + "'>"
        "<div style='display:flex;align-items:center;gap:12px;margin-bottom:10px'>"
        "<span style='background:" + regime["color"] + ";color:#fff;font-weight:600;font-size:13px;padding:3px 14px;border-radius:99px'>" + regime["label"] + "</span>"
        "<span style='font-size:14px;font-weight:500;color:" + regime["color"] + "'>" + regime["action"] + "</span>"
        "<span style='margin-left:auto;font-size:13px;color:#888'>Score: " + str(regime["total"]) + "/8</span>"
        "</div>"
        "<div style='display:grid;grid-template-columns:repeat(4,1fr);gap:8px;font-size:12px'>"
        "<div style='background:rgba(255,255,255,.7);border-radius:8px;padding:8px 10px'><div style='color:#888;margin-bottom:2px'>SPY trend</div><div style='font-weight:600;color:" + regime["color"] + "'>" + str(regime["spy_pts"]) + "/2</div><div style='color:#888'>$" + str(regime["spy_price"]) + "</div></div>"
        "<div style='background:rgba(255,255,255,.7);border-radius:8px;padding:8px 10px'><div style='color:#888;margin-bottom:2px'>Advance/Decline</div><div style='font-weight:600;color:" + regime["color"] + "'>" + str(regime["ad_pts"]) + "/2</div><div style='color:#888'>" + str(int(regime["ad_pct"])) + "% above SMA50</div></div>"
        "<div style='background:rgba(255,255,255,.7);border-radius:8px;padding:8px 10px'><div style='color:#888;margin-bottom:2px'>New High/Low</div><div style='font-weight:600;color:" + regime["color"] + "'>" + str(regime["hl_pts"]) + "/2</div><div style='color:#888'>QQQ " + str(regime["qqq_hi"]) + "% of high</div></div>"
        "<div style='background:rgba(255,255,255,.7);border-radius:8px;padding:8px 10px'><div style='color:#888;margin-bottom:2px'>VIX</div><div style='font-weight:600;color:" + regime["color"] + "'>" + str(regime["vix_pts"]) + "/2</div><div style='color:#888'>" + str(regime["vix"]) + "</div></div>"
        "</div></div>"
    )

    css = "* {box-sizing:border-box;margin:0;padding:0} body{font-family:-apple-system,sans-serif;background:#f5f5f7;color:#1d1d1f;font-size:14px} .hdr{background:#1d1d1f;color:#fff;padding:22px 30px} .hdr h1{font-size:20px;font-weight:600} .hdr p{color:#aaa;font-size:13px;margin-top:3px} .mx{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;padding:16px 30px} .mc{background:#fff;border-radius:10px;padding:13px 16px;box-shadow:0 1px 3px rgba(0,0,0,.08)} .ml{font-size:12px;color:#888;margin-bottom:3px} .mv{font-size:24px;font-weight:600} .fl{padding:0 30px 12px;display:flex;gap:10px;flex-wrap:wrap;align-items:center;font-size:13px;color:#555} select,input{font-size:13px;padding:5px 10px;border:1px solid #ddd;border-radius:7px;background:#fff} button{padding:5px 13px;border:1px solid #ddd;border-radius:7px;background:#fff;cursor:pointer} .tw{padding:0 30px 30px;overflow-x:auto} table{width:100%;border-collapse:collapse;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.08)} th{background:#f5f5f7;text-align:left;padding:9px 11px;font-size:12px;color:#555;font-weight:600;border-bottom:1px solid #e8e8e8;cursor:pointer;white-space:nowrap} th:hover{background:#eaeaea} td{padding:9px 11px;border-bottom:1px solid #f0f0f0;vertical-align:middle} tr:last-child td{border-bottom:none} tr:hover td{background:#fafafa} .ft{padding:14px 30px;color:#aaa;font-size:12px;text-align:center}"
    js = "function ft(){var q=document.getElementById('sb').value.toLowerCase(),ep=parseFloat(document.getElementById('es').value)||0,rv=parseFloat(document.getElementById('rs').value)||0;document.querySelectorAll('#tb tr').forEach(function(tr){var t=tr.innerText.toLowerCase(),ev=parseFloat((tr.cells[6]?tr.cells[6].innerText:'').replace(/[+%]/g,''))/100||0,rsv=parseFloat(tr.cells[5]?tr.cells[5].innerText:0)||0;tr.style.display=(t.indexOf(q)>=0&&ev>=ep&&rsv>=rv)?'':'none';});}function rst(){document.getElementById('sb').value='';document.getElementById('es').value='';document.getElementById('rs').value='';ft();}var sd={};function st(c){var tb=document.getElementById('tb'),rows=Array.from(tb.rows).filter(function(r){return r.style.display!=='none';});sd[c]=!sd[c];rows.sort(function(a,b){var av=a.cells[c]?a.cells[c].innerText.replace(/[^0-9.-]/g,''):'0',bv=b.cells[c]?b.cells[c].innerText.replace(/[^0-9.-]/g,''):'0';var an=parseFloat(av),bn=parseFloat(bv);if(!isNaN(an)&&!isNaN(bn))return sd[c]?an-bn:bn-an;return sd[c]?av.localeCompare(bv):bv.localeCompare(av);});rows.forEach(function(r){tb.appendChild(r);});}"

    html  = "<!DOCTYPE html><html><head><meta charset='UTF-8'><title>Minervini " + date + "</title><style>" + css + "</style></head><body>"
    html += "<div class='hdr'><h1>&#9889; Minervini Scanner &mdash; USIC 2026</h1><p>Date: " + date + " | Scanned: " + str(total) + " | Passed: " + str(len(res)) + "</p></div>"
    html += regime_html
    html += "<div class='mx'><div class='mc'><div class='ml'>Passed</div><div class='mv'>" + str(len(res)) + "</div></div><div class='mc'><div class='ml'>Avg RS</div><div class='mv'>" + str(avg_rs) + "</div></div><div class='mc'><div class='ml'>Within 5% of high</div><div class='mv'>" + str(near5) + "</div></div><div class='mc'><div class='ml'>Avg EPS</div><div class='mv'>+" + str(avg_ep) + "%</div></div></div>"
    html += "<div class='fl'><span>Search:</span><input id='sb' placeholder='ticker...' oninput='ft()' style='width:120px'><span>EPS&ge;:</span><select id='es' onchange='ft()'><option value=''>All</option><option value='0.5'>50%</option><option value='1'>100%</option><option value='2'>200%</option></select><span>RS&ge;:</span><select id='rs' onchange='ft()'><option value=''>All</option><option value='70'>70</option><option value='80'>80</option><option value='90'>90</option></select><button onclick='rst()'>Reset</button></div>"
    html += "<div class='tw'><table><thead><tr><th onclick='st(0)'>Ticker</th><th onclick='st(1)'>Sector</th><th onclick='st(2)'>Price</th><th onclick='st(3)'>From High</th><th onclick='st(4)'>Trend Score</th><th onclick='st(5)'>RS</th><th onclick='st(6)'>EPS</th><th onclick='st(7)'>Revenue</th><th onclick='st(8)'>Vol Ratio</th><th onclick='st(9)'>Mkt Cap</th></tr></thead><tbody id='tb'>" + rows + "</tbody></table></div>"
    html += "<div class='ft'>Research only | " + datetime.now().strftime("%Y-%m-%d %H:%M") + "</div>"
    html += "<script>" + js + "</script></body></html>"
    return html

if __name__ == "__main__":
    print("=" * 60)
    print("  Minervini Scanner v3 - USIC 2026")
    print("  Scanning " + str(len(WATCHLIST)) + " stocks...")
    print("=" * 60)
    spy = yf.Ticker("SPY").history(period="1y")
    print("SPY ready (" + str(len(spy)) + " days)")
    print("Checking market regime...")
    regime = get_market_regime()
    print("MARKET REGIME: " + regime["label"] + " (" + str(regime["total"]) + "/8)")
    print()
    results = []
    for i, ticker in enumerate(WATCHLIST, 1):
        print("  [" + str(i).rjust(3) + "/" + str(len(WATCHLIST)) + "] " + ticker.ljust(6) + " ", end="", flush=True)
        d = analyze(ticker, spy)
        if d is None:
            print("skip (no data)")
            time.sleep(0.5)
            continue
        ok = (
            d["score"] >= MIN_TREND and
            (d["rs"] or 0) >= MIN_RS and
            ((d["eps"] is not None and d["eps"] >= MIN_EPS) or
             (d["rev"] is not None and d["rev"] >= MIN_REV)) and
            abs(d["dist"] / 100) <= MAX_DIST
        )
        if ok:
            results.append(d)
            print("PASS  Score=" + str(d["score"]) + "/8  RS=" + str(d["rs"]) + "  EPS=" + pct(d["eps"]) + "  Dist=" + str(d["dist"]) + "%")
        else:
            print("skip")
        time.sleep(0.8)

    results.sort(key=lambda x: x["dist"], reverse=True)
    date      = datetime.now().strftime("%Y-%m-%d")
    html_file = "minervini_" + date + ".html"
    csv_file  = "minervini_" + date + ".csv"

    with open(html_file, "w", encoding="utf-8") as f:
        f.write(make_html(results, date, len(WATCHLIST), regime))

    if results:
        pd.DataFrame([{
            "Ticker": r["ticker"], "Sector": r["sector"], "Price": r["price"],
            "TrendScore": str(r["score"]) + "/8", "RS": r["rs"],
            "FromHigh": str(r["dist"]) + "%",
            "EPS": pct(r["eps"]), "Revenue": pct(r["rev"]), "ScanDate": date,
        } for r in results]).to_csv(csv_file, index=False, encoding="utf-8-sig")

    print()
    print("=" * 60)
    print("  DONE! " + str(len(results)) + " stocks passed:")
    for r in results:
        print("  * " + r["ticker"].ljust(6) + "  RS=" + str(r["rs"] or "N/A") + "  EPS=" + pct(r["eps"]) + "  Dist=" + str(r["dist"]) + "%")
    abs_path = os.path.abspath(html_file)
    win_path = abs_path.replace("/home/wahmui", "\\\\wsl.localhost\\Ubuntu\\home\\wahmui")
    print()
    print("  HTML saved: " + html_file)
    print("  Open in Windows: " + win_path)
    print("=" * 60)
    input("\nPress Enter to close...")
