from __future__ import annotations

import csv
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent
REPORTS_DIR = ROOT / "reports"
JOURNAL_DIR = ROOT / "journal"
JOURNAL_PATH = JOURNAL_DIR / "trades.csv"
SCANNER_SCRIPT = ROOT / "minervini_scanner.py"

TRADINGVIEW_EXCHANGES = {
    # Common current scanner universe names. Unknowns fall back to ticker-only search.
    "AAPL": "NASDAQ", "MSFT": "NASDAQ", "AMZN": "NASDAQ", "GOOGL": "NASDAQ", "META": "NASDAQ",
    "NVDA": "NASDAQ", "AVGO": "NASDAQ", "AMD": "NASDAQ", "TSLA": "NASDAQ", "ARM": "NASDAQ",
    "PLTR": "NASDAQ", "NFLX": "NASDAQ", "MU": "NASDAQ", "MRVL": "NASDAQ", "KLAC": "NASDAQ",
    "LRCX": "NASDAQ", "AMAT": "NASDAQ", "ASML": "NASDAQ", "MPWR": "NASDAQ", "MCHP": "NASDAQ",
    "NXPI": "NASDAQ", "ONTO": "NYSE", "ACLS": "NASDAQ", "FORM": "NASDAQ", "CRWD": "NASDAQ",
    "SNOW": "NYSE", "DDOG": "NASDAQ", "MDB": "NASDAQ", "HUBS": "NYSE", "APP": "NASDAQ",
    "TTD": "NASDAQ", "PANW": "NASDAQ", "FTNT": "NASDAQ", "ZS": "NASDAQ", "NET": "NYSE",
    "WDAY": "NASDAQ", "ADSK": "NASDAQ", "NOW": "NYSE", "ADBE": "NASDAQ", "TWLO": "NYSE",
    "AI": "NYSE", "CLS": "NYSE", "VRT": "NYSE", "RKLB": "NASDAQ", "DKNG": "NASDAQ",
    "MSTR": "NASDAQ", "UPST": "NASDAQ", "FRPT": "NASDAQ", "COIN": "NASDAQ", "V": "NYSE",
    "MA": "NYSE", "HOOD": "NASDAQ", "XYZ": "NYSE", "PYPL": "NASDAQ", "GS": "NYSE",
    "MS": "NYSE", "BAC": "NYSE", "AXP": "NYSE", "BLK": "NYSE", "SCHW": "NYSE",
    "COST": "NASDAQ", "BKNG": "NASDAQ", "MELI": "NASDAQ", "SHOP": "NASDAQ", "UBER": "NYSE",
    "ABNB": "NASDAQ", "DUOL": "NASDAQ", "ELF": "NYSE", "CELH": "NASDAQ", "WING": "NASDAQ",
    "CVNA": "NYSE", "LLY": "NYSE", "VRTX": "NASDAQ", "REGN": "NASDAQ", "ISRG": "NASDAQ",
    "AMGN": "NASDAQ", "TMO": "NYSE", "DHR": "NYSE", "SPOT": "NYSE", "EA": "NASDAQ",
    "COHR": "NYSE", "LITE": "NASDAQ", "AAOI": "NASDAQ", "VIAV": "NASDAQ", "CIEN": "NYSE",
    "ANET": "NYSE", "PENG": "NASDAQ", "ALAB": "NASDAQ", "CRWV": "NASDAQ", "BRK-B": "NYSE",
}

ALERT_SECTIONS = ["Actionable Today", "Watch Tomorrow", "Leadership But Not Buyable"]


@dataclass
class TradePlan:
    ticker: str
    setup: str
    entry_trigger: str
    stop: str
    risk_pct: str
    planned_size: str
    status: str = "Planned"
    notes: str = ""
    created_at: str = ""

    def to_row(self) -> dict[str, str]:
        row = asdict(self)
        if not row["created_at"]:
            row["created_at"] = datetime.now().isoformat(timespec="seconds")
        return row


def tradingview_link(ticker: str) -> str:
    ticker = ticker.strip().upper()
    tv_ticker = ticker.replace("-", ".")
    exchange = TRADINGVIEW_EXCHANGES.get(ticker)
    symbol = f"{exchange}:{tv_ticker}" if exchange else tv_ticker
    return f"https://www.tradingview.com/chart/?symbol={symbol}"


def latest_html_report(reports_dir: Path = REPORTS_DIR) -> Path | None:
    latest = reports_dir / "Minervini_Scanner_Latest_v3.html"
    if latest.exists():
        return latest
    reports = sorted(reports_dir.glob("minervini_*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
    return reports[0] if reports else None


def latest_markdown_alert(reports_dir: Path = REPORTS_DIR) -> Path | None:
    reports = sorted(reports_dir.glob("minervini_alerts_*.md"), key=lambda p: p.name, reverse=True)
    return reports[0] if reports else None


def parse_alert_line(line: str) -> dict[str, object] | None:
    # Example: - **DDOG** — Score 90 | Tier A | Pivot Approaching | RS 90 | Pivot $271.54 (-0.3%) | Entry: ...
    match = re.match(r"- \*\*(?P<ticker>[^*]+)\*\* — Score (?P<score>\d+) \| (?P<body>.*)", line.strip())
    if not match:
        return None
    body = match.group("body")
    parts = [p.strip() for p in body.split(" | ")]
    result = {"ticker": match.group("ticker"), "score": int(match.group("score")), "raw": line.strip()}
    if parts:
        result["tier"] = parts[0].replace("Tier ", "")
    if len(parts) > 1:
        result["setup"] = parts[1]
    if len(parts) > 2:
        result["rs"] = parts[2].replace("RS ", "")
    for part in parts:
        if part.startswith("Pivot "):
            result["pivot"] = part.replace("Pivot ", "")
        elif part.startswith("Entry:"):
            result["entry"] = part.replace("Entry:", "").strip()
        elif part.startswith("Stop:"):
            result["stop"] = part.replace("Stop:", "").strip()
        elif part.startswith("Risk:"):
            result["risk"] = part.replace("Risk:", "").strip()
        elif part.startswith("Invalidation:"):
            result["invalidation"] = part.replace("Invalidation:", "").strip()
    result["chart"] = tradingview_link(str(result["ticker"]))
    return result


def parse_markdown_alert_sections(text: str) -> dict[str, list[dict[str, object]]]:
    sections = {name: [] for name in ALERT_SECTIONS}
    current = None
    for line in text.splitlines():
        if line.startswith("## "):
            title = line[3:].strip()
            current = title if title in sections else None
            continue
        if current and line.startswith("- **"):
            parsed = parse_alert_line(line)
            if parsed:
                sections[current].append(parsed)
    return sections


def append_trade_plan(path: Path, plan: TradePlan) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(asdict(plan).keys())
    exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        writer.writerow(plan.to_row())


def read_trade_journal(path: Path = JOURNAL_PATH) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def run_scanner() -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCANNER_SCRIPT)], cwd=str(ROOT), text=True, capture_output=True)


def open_path(path: Path) -> None:
    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def render_app() -> None:
    import streamlit as st

    st.set_page_config(page_title="Minervini Control Center", page_icon="📈", layout="wide")
    st.title("📈 Minervini Scanner Control Center")
    st.caption("USIC preparation dashboard — run scans, review top focus names, open charts, and maintain a trade plan.")

    with st.sidebar:
        st.header("Controls")
        mode = st.selectbox("Scan Mode", ["Focus", "Competition", "Discovery"], help="v1.0 runs the current focus universe; broader universe modes are reserved for v3.2.")
        portfolio_value = st.number_input("Portfolio value", min_value=1000, value=100000, step=5000)
        risk_per_trade = st.selectbox("Risk per trade", ["0.5%", "1.0%", "1.5%"], index=1)
        st.info(f"Mode selected: {mode}. Portfolio ${portfolio_value:,.0f}; risk {risk_per_trade}.")
        if st.button("▶ Run Scanner", type="primary", use_container_width=True):
            with st.spinner("Running Minervini scanner..."):
                result = run_scanner()
            if result.returncode == 0:
                st.success("Scan completed.")
                st.code(result.stdout[-4000:])
            else:
                st.error("Scanner failed.")
                st.code((result.stdout + "\n" + result.stderr)[-4000:])
        html = latest_html_report()
        md = latest_markdown_alert()
        if html and st.button("🌐 Open Latest HTML", use_container_width=True):
            open_path(html)
        if md and st.button("📝 Open Markdown Alerts", use_container_width=True):
            open_path(md)

    md_path = latest_markdown_alert()
    html_path = latest_html_report()
    col1, col2, col3 = st.columns(3)
    col1.metric("Latest HTML", html_path.name if html_path else "Not found")
    col2.metric("Latest Alerts", md_path.name if md_path else "Not found")
    col3.metric("Journal trades", len(read_trade_journal()))

    if not md_path:
        st.warning("No markdown alert report found. Run the scanner first.")
        return

    alert_text = md_path.read_text(encoding="utf-8")
    sections = parse_markdown_alert_sections(alert_text)
    tabs = st.tabs(ALERT_SECTIONS + ["Trade Journal", "Raw Alerts"])

    for tab, section_name in zip(tabs[:3], ALERT_SECTIONS):
        with tab:
            rows = sections[section_name]
            if not rows:
                st.info("No names in this section.")
                continue
            for row in rows:
                with st.container(border=True):
                    cols = st.columns([1, 1, 2, 2, 1])
                    cols[0].subheader(str(row["ticker"]))
                    cols[1].metric("Score", row.get("score", ""))
                    cols[2].write(f"**Setup:** {row.get('setup', '')}\n\n**Pivot:** {row.get('pivot', '')}")
                    cols[3].write(f"**Entry:** {row.get('entry', '')}\n\n**Stop/Risk:** {row.get('stop', '')} / {row.get('risk', '')}")
                    cols[4].link_button("Open Chart", str(row["chart"]), use_container_width=True)
                    with st.expander("Add to trade plan"):
                        with st.form(f"plan-{row['ticker']}-{section_name}"):
                            entry = st.text_input("Entry trigger", value=str(row.get("entry", "")))
                            stop = st.text_input("Stop", value=str(row.get("stop", "")))
                            risk = st.text_input("Risk %", value=str(row.get("risk", "")).replace("%", ""))
                            size = st.text_input("Planned shares / size", value="")
                            notes = st.text_area("Notes", value=str(row.get("invalidation", "")))
                            submitted = st.form_submit_button("Save plan")
                            if submitted:
                                append_trade_plan(JOURNAL_PATH, TradePlan(
                                    ticker=str(row["ticker"]), setup=str(row.get("setup", "")),
                                    entry_trigger=entry, stop=stop, risk_pct=risk,
                                    planned_size=size, notes=notes,
                                ))
                                st.success(f"Saved {row['ticker']} to trade journal.")

    with tabs[3]:
        journal = read_trade_journal()
        if journal:
            st.dataframe(journal, use_container_width=True)
        else:
            st.info("No trade plans yet.")

    with tabs[4]:
        st.markdown(alert_text)


if __name__ == "__main__":
    render_app()
