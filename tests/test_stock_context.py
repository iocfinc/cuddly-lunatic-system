from __future__ import annotations

import datetime as dt
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quant_researcher_desk.stock_context import DailyBar, compute_trend_regime  # noqa: E402


def _daily_bars(closes: list[float]) -> list[DailyBar]:
    start = dt.date(2025, 1, 1)
    return [
        DailyBar(date=(start + dt.timedelta(days=index)).isoformat(), close=close)
        for index, close in enumerate(closes)
    ]


def test_compute_trend_regime_classifies_bullish_stack_and_positive_slopes() -> None:
    closes = [100.0 + index * 0.8 for index in range(250)]

    regime = compute_trend_regime(_daily_bars(closes))

    assert regime == "bullish"


def test_compute_trend_regime_classifies_bearish_stack_and_negative_slopes() -> None:
    closes = [300.0 - index * 0.75 for index in range(250)]

    regime = compute_trend_regime(_daily_bars(closes))

    assert regime == "bearish"


def test_compute_trend_regime_returns_mixed_when_stack_or_slopes_break() -> None:
    closes = [150.0 + index * 0.25 for index in range(230)] + [190.0 - index * 1.4 for index in range(20)]

    regime = compute_trend_regime(_daily_bars(closes))

    assert regime == "mixed"
