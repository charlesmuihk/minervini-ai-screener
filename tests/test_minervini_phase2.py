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
