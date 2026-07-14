import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import control_center as cc


def test_parse_markdown_alert_sections_extracts_actionable_tickers():
    text = """# Minervini v3.1 Alerts — 2099-01-01
Market: **BULL 7/8** | Position sizing: **100% — 5-6 positions**
## Actionable Today
- **DDOG** — Score 90 | Tier A | Pivot Approaching | RS 90 | Pivot $271.54 (-0.3%) | Entry: $271.54 pivot zone | Stop: $255.25 | Risk: 5.7% | Invalidation: close below $255.25
## Watch Tomorrow
- **AMD** — Score 79 | Tier B | Setup Forming | RS 95 | Pivot $584.73 (-6.3%) | Entry: watch below $584.73; act only near/through pivot | Stop: $495.35 | Risk: 9.6% | Invalidation: close below $495.35
## Leadership But Not Buyable
- **MU** — Score 60 | Tier C | Leadership Candidate | RS 99 | Pivot $1,254.81 (-21.7%) | Entry: $1,254.81 pivot zone | Stop: $891.66 | Risk: 9.3% | Invalidation: close below $891.66
"""
    sections = cc.parse_markdown_alert_sections(text)

    assert sections["Actionable Today"][0]["ticker"] == "DDOG"
    assert sections["Actionable Today"][0]["score"] == 90
    assert sections["Watch Tomorrow"][0]["ticker"] == "AMD"
    assert sections["Leadership But Not Buyable"][0]["ticker"] == "MU"


def test_tradingview_link_uses_exchange_mapping_and_fallback():
    assert cc.tradingview_link("DDOG") == "https://www.tradingview.com/chart/?symbol=NASDAQ:DDOG"
    assert cc.tradingview_link("NET") == "https://www.tradingview.com/chart/?symbol=NYSE:NET"
    assert cc.tradingview_link("BRK-B") == "https://www.tradingview.com/chart/?symbol=NYSE:BRK.B"
    assert cc.tradingview_link("UNKNOWN") == "https://www.tradingview.com/chart/?symbol=UNKNOWN"


def test_append_trade_plan_creates_csv_with_expected_fields(tmp_path):
    journal = tmp_path / "trades.csv"
    row = cc.TradePlan(
        ticker="DDOG",
        setup="Pivot Approaching",
        entry_trigger="Break $271.54 with volume",
        stop="255.25",
        risk_pct="1.0",
        planned_size="143",
        status="Planned",
        notes="Test plan",
    )

    cc.append_trade_plan(journal, row)

    with journal.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["ticker"] == "DDOG"
    assert rows[0]["status"] == "Planned"
    assert rows[0]["entry_trigger"] == "Break $271.54 with volume"


def test_latest_report_helpers_find_newest_files(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    older = reports / "minervini_alerts_2099-01-01.md"
    newer = reports / "minervini_alerts_2099-01-02.md"
    html = reports / "Minervini_Scanner_Latest_v3.html"
    older.write_text("old", encoding="utf-8")
    newer.write_text("new", encoding="utf-8")
    html.write_text("html", encoding="utf-8")

    assert cc.latest_markdown_alert(reports) == newer
    assert cc.latest_html_report(reports) == html
