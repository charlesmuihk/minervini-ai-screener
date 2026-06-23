
import pandas as pd
import json, os

# Load both trade files
t1 = pd.read_csv(os.path.expanduser("~/minervini-ai-screener/portfolio_trades.csv"))

# Rebuild equity curves from trades
import yfinance as yf
import numpy as np
from datetime import datetime

def build_equity(trades_df, initial=100000):
    trades_df = trades_df.copy()
    trades_df["entry_date"] = pd.to_datetime(trades_df["entry_date"])
    trades_df["exit_date"]  = pd.to_datetime(trades_df["exit_date"])
    dates = pd.date_range("2020-01-01", "2025-12-31", freq="ME")
    equity = [initial]
    cap = initial
    for d in dates:
        month_exits = trades_df[trades_df["exit_date"].dt.to_period("M") == d.to_period("M")]
        for _, t in month_exits.iterrows():
            cap *= (1 + t["ret"]/100 * 0.25)
        equity.append(cap)
    return dates.tolist(), equity[1:]

spy = yf.Ticker("SPY").history(start="2020-01-01", end="2025-12-31")
spy_monthly = spy["Close"].resample("ME").last()
spy_ret = (spy_monthly / spy_monthly.iloc[0] * 100000).tolist()
spy_dates = spy_monthly.index.strftime("%Y-%m-%d").tolist()

dates1, eq1 = build_equity(t1)
dates_str = [d.strftime("%Y-%m-%d") for d in dates1]

# Year stats
yearly = {}
t1["year"] = pd.to_datetime(t1["entry_date"]).dt.year
for yr in range(2020, 2026):
    y = t1[t1["year"]==yr]
    if len(y):
        w = y[y["ret"]>0]
        yearly[yr] = {"trades": len(y), "win": round(len(w)/len(y)*100), "avg": round(y["ret"].mean(),1)}

data = {
    "dates": dates_str,
    "equity_v1": [round(e) for e in eq1],
    "spy": spy_ret[:len(dates_str)],
    "spy_dates": spy_dates[:len(dates_str)],
    "yearly": yearly,
    "trades": t1[["ticker","entry_date","ret","tier","is_vcp","exit_reason"]].head(20).to_dict("records"),
}

out = os.path.expanduser("~/minervini-ai-screener/chart_data.json")
with open(out, "w") as f:
    json.dump(data, f, default=str)
print(f"Data saved: {out}")
