import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import minervini_scanner as m


def test_load_watchlist_prefers_external_csv_and_deduplicates(tmp_path):
    watchlist = tmp_path / "watchlist.csv"
    watchlist.write_text("ticker,theme\nanet,AI Networking\nPENG,AI\nANET,duplicate\n# comment\n", encoding="utf-8")
    assert m.load_watchlist(watchlist) == ["ANET", "PENG"]


def test_rs_percentiles_rank_universe_without_everything_becoming_99():
    scores = {"AAA": 0.50, "BBB": 0.20, "CCC": -0.10, "DDD": 0.05}
    ranked = m.calc_rs_percentiles(scores)
    assert ranked["AAA"] == 99
    assert ranked["CCC"] == 1
    assert ranked["BBB"] > ranked["DDD"]
    assert len(set(ranked.values())) > 2


def test_earnings_risk_classification():
    today = date(2026, 7, 9)
    assert m.classify_earnings_risk(today + timedelta(days=3), today=today)[0] == "High"
    assert m.classify_earnings_risk(today + timedelta(days=8), today=today)[0] == "Medium"
    assert m.classify_earnings_risk(today + timedelta(days=15), today=today)[0] == "Watch"
    assert m.classify_earnings_risk(today + timedelta(days=40), today=today)[0] == "Low"


def test_position_size_uses_risk_budget_and_stop_distance():
    result = m.calc_position_size(portfolio_value=100_000, risk_pct=1.0, entry_price=177, stop_price=170)
    assert result["dollar_risk"] == 1000
    assert result["stop_risk_pct"] == 4.0
    assert result["shares"] == 143


def test_detect_vcp_details_exposes_contractions():
    close = []
    close += [110 + i * 0.6 for i in range(80)]
    close += [176, 168, 155, 142, 137, 145, 155, 165, 177, 170, 162, 155, 160, 168, 176, 172, 168, 162, 166, 172, 179, 181]
    volume = [2_000_000] * 80 + [2_000_000] * 5 + [1_700_000] * 8 + [1_000_000] * 9
    df = m.pd.DataFrame(
        {
            "Open": close,
            "High": [x * 1.01 for x in close],
            "Low": [x * 0.99 for x in close],
            "Close": close,
            "Volume": volume,
        },
        index=m.pd.date_range("2026-01-01", periods=len(close), freq="B"),
    )
    details = m.detect_vcp_details(df)
    assert details["is_vcp"] is True
    assert details["score"] >= 6
    assert len(details["contractions"]) >= 2
    assert "depth_pct" in details["contractions"][-1]


def test_report_renders_v3_branding_and_latest_copy():
    rd = {
        "regime": "BULL",
        "label": "test regime",
        "score": 7,
        "spy": 500.0,
        "spy_pts": 2,
        "adv_pts": 2,
        "nh_pts": 1,
        "vix": 18.0,
        "vix_pts": 2,
        "qqq_pct": 96.0,
        "pos_pct": 100,
        "max_pos": "5-6 positions",
    }
    scan_date = "2099-01-01"
    report_path = Path(m.save_report([], rd, scan_date))
    latest_path = report_path.with_name(m.LATEST_REPORT_NAME)
    try:
        html = report_path.read_text(encoding="utf-8")
        latest_html = latest_path.read_text(encoding="utf-8")
        assert f"Minervini {m.SCANNER_VERSION}" in html
        assert "Minervini Scanner v2.0" not in html
        assert latest_html == html
    finally:
        report_path.unlink(missing_ok=True)
        latest_path.unlink(missing_ok=True)


def sample_result(ticker, tier, rs, pivot_dist, setup_status, vcp_score, earnings_risk="Low"):
    return {
        "ticker": ticker,
        "tier": tier,
        "rs": rs,
        "trend": 8,
        "pivot_dist": pivot_dist,
        "stop_risk_pct": 6.0,
        "vcp_score": vcp_score,
        "earnings_risk": earnings_risk,
        "setup_status": setup_status,
        "pattern": "VCP" if vcp_score else "BASE",
        "price": 100.0,
        "pivot_price": 101.0,
        "stop": 94.0,
        "shares": 166,
        "position_value": 16600.0,
    }


def test_actionability_score_rewards_near_pivot_vcp_and_penalizes_earnings():
    clean = sample_result("DDOG", "A", 90, -0.3, "Pivot Approaching", 8, "Low")
    risky = sample_result("RISK", "A", 90, -0.3, "Pivot Approaching", 8, "High")
    far = sample_result("MU", "C", 99, -21.7, "Leadership Candidate", 0, "Low")

    assert m.calculate_actionability_score(clean) >= 85
    assert m.calculate_actionability_score(risky) < m.calculate_actionability_score(clean)
    assert m.calculate_actionability_score(far) < 70


def test_focus_lists_prioritize_actionable_today_then_watch_tomorrow():
    results = [
        sample_result("MU", "C", 99, -21.7, "Leadership Candidate", 0),
        sample_result("DDOG", "A", 90, -0.3, "Pivot Approaching", 8),
        sample_result("AMD", "B", 95, -6.3, "Setup Forming", 7),
        sample_result("NET", "B", 72, 0.6, "Actionable Pivot", 7),
    ]
    focus = m.build_focus_lists(results, limit=3)

    assert [r["ticker"] for r in focus["actionable_today"]][:2] == ["DDOG", "NET"]
    assert [r["ticker"] for r in focus["watch_tomorrow"]] == ["AMD"]
    assert [r["ticker"] for r in focus["leadership_not_buyable"]] == ["MU"]


def test_markdown_alert_report_contains_focus_sections_and_trade_plan():
    rd = {"regime": "BULL", "score": 7, "pos_pct": 100, "max_pos": "5-6 positions"}
    results = [sample_result("DDOG", "A", 90, -0.3, "Pivot Approaching", 8)]
    report_path = Path(m.save_markdown_alert(results, rd, "2099-01-02"))
    try:
        text = report_path.read_text(encoding="utf-8")
        assert "Minervini v3.1 Alerts" in text
        assert "Actionable Today" in text
        assert "DDOG" in text
        assert "Entry" in text and "Stop" in text and "Risk" in text
    finally:
        report_path.unlink(missing_ok=True)
