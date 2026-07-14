import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import minervini_scanner as m


def make_df(close, volume=None):
    dates = pd.date_range("2026-01-01", periods=len(close), freq="B")
    if volume is None:
        volume = [1_000_000] * len(close)
    return pd.DataFrame(
        {
            "Open": close,
            "High": [x * 1.01 for x in close],
            "Low": [x * 0.99 for x in close],
            "Close": close,
            "Volume": volume,
        },
        index=dates,
    )


def test_watchlist_includes_current_ai_infrastructure_leaders():
    for ticker in ["ANET", "PENG", "ALAB", "CRWV"]:
        assert ticker in m.WATCHLIST


def test_watchlist_uses_current_block_ticker_xyz_not_stale_sq():
    assert "XYZ" in m.WATCHLIST
    assert "SQ" not in m.WATCHLIST


def test_classify_setup_status_marks_retest_zone_as_retest_watch():
    status = m.classify_setup_status(
        current_price=177,
        pivot_price=181,
        stop_price=170,
        breakout_occurred=True,
        quiet_volume_ratio=0.65,
    )
    assert status == "Retest Watch"


def test_classify_setup_status_marks_far_above_pivot_as_extended():
    status = m.classify_setup_status(
        current_price=200,
        pivot_price=181,
        stop_price=170,
        breakout_occurred=True,
        quiet_volume_ratio=1.0,
    )
    assert status == "Extended"


def test_detect_base_and_pivot_uses_recent_local_resistance_not_old_low():
    # Earlier old low/pivot around 100 should be ignored; recent base resistance is near 181.
    close = []
    close += [100 + i * 0.2 for i in range(80)]
    close += [120 + i * 0.7 for i in range(80)]
    close += [176, 170, 162, 155, 160, 166, 172, 177, 169, 163, 166, 172, 178, 181, 180, 179, 181, 180, 184]
    df = make_df(close)
    result = m.detect_base_and_pivot(df, lookback=40)
    assert result is not None
    assert 180 <= result["pivot_price"] <= 183
    assert result["distance_from_pivot_pct"] <= 5


def test_detect_vcp_scores_progressively_shallower_contractions():
    close = []
    close += [110 + i * 0.6 for i in range(80)]
    close += [176, 168, 155, 142, 137, 145, 155, 165, 177, 170, 162, 155, 160, 168, 176, 172, 168, 162, 166, 172, 179, 181]
    volume = [2_000_000] * 80 + [2_000_000] * 5 + [1_700_000] * 8 + [1_000_000] * 9
    df = make_df(close, volume)
    is_vcp, score, pivot = m.detect_vcp(df)
    assert is_vcp
    assert score >= 6
    assert 179 <= pivot <= 183
