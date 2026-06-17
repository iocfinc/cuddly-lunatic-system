"""Stock-first context and deterministic review helpers for weekly options flows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from quant_researcher_desk.moomoo_options_report import OptionsReportError, as_float, get_first


TrendRegime = str
StockDirection = str


@dataclass(frozen=True)
class DailyBar:
    date: str
    close: float


@dataclass(frozen=True)
class StockContext:
    symbol: str
    bars: tuple[DailyBar, ...]
    latest_close: float
    ma20: float
    ma50: float
    ma200: float
    ma20_slope: float
    ma50_slope: float
    trend_regime: TrendRegime


@dataclass(frozen=True)
class StockReviewResult:
    direction: StockDirection
    trend_regime: TrendRegime
    thesis_summary: str
    invalidation: str
    catalyst_view: str
    review_confidence: str
    countertrend_risk: str
    model_used: str | None = None


def daily_bars_from_rows(rows: list[dict[str, Any]]) -> tuple[DailyBar, ...]:
    bars: list[DailyBar] = []
    for row in rows:
        close = as_float(get_first(row, "close", "last_close", default=None))
        date = str(get_first(row, "time_key", "date", "time", default="")).strip()[:10]
        if close is None or not date:
            continue
        bars.append(DailyBar(date=date, close=float(close)))
    return tuple(bars)


def _moving_average(values: list[float], window: int) -> float:
    if len(values) < window:
        raise OptionsReportError(f"Need at least {window} daily closes to compute moving averages.")
    sample = values[-window:]
    return sum(sample) / len(sample)


def _moving_average_slope(values: list[float], window: int) -> float:
    if len(values) < window + 1:
        raise OptionsReportError(f"Need at least {window + 1} daily closes to compute moving-average slopes.")
    current = _moving_average(values, window)
    prior = _moving_average(values[:-1], window)
    return current - prior


def compute_trend_regime(bars: list[DailyBar] | tuple[DailyBar, ...]) -> TrendRegime:
    closes = [bar.close for bar in bars]
    ma20 = _moving_average(closes, 20)
    ma50 = _moving_average(closes, 50)
    ma200 = _moving_average(closes, 200)
    ma20_slope = _moving_average_slope(closes, 20)
    ma50_slope = _moving_average_slope(closes, 50)
    latest_close = closes[-1]
    if latest_close > ma20 > ma50 > ma200 and ma20_slope > 0 and ma50_slope > 0:
        return "bullish"
    if latest_close < ma20 < ma50 < ma200 and ma20_slope < 0 and ma50_slope < 0:
        return "bearish"
    return "mixed"


def build_stock_context(symbol: str, rows: list[dict[str, Any]]) -> StockContext:
    bars = daily_bars_from_rows(rows)
    closes = [bar.close for bar in bars]
    if len(closes) < 200:
        raise OptionsReportError(f"Need at least 200 daily bars to classify trend regime for {symbol}.")
    ma20 = _moving_average(closes, 20)
    ma50 = _moving_average(closes, 50)
    ma200 = _moving_average(closes, 200)
    ma20_slope = _moving_average_slope(closes, 20)
    ma50_slope = _moving_average_slope(closes, 50)
    return StockContext(
        symbol=symbol,
        bars=bars,
        latest_close=closes[-1],
        ma20=ma20,
        ma50=ma50,
        ma200=ma200,
        ma20_slope=ma20_slope,
        ma50_slope=ma50_slope,
        trend_regime=compute_trend_regime(bars),
    )


def fallback_stock_review(context: StockContext) -> StockReviewResult:
    if context.trend_regime == "bullish":
        return StockReviewResult(
            direction="bullish",
            trend_regime=context.trend_regime,
            thesis_summary=(
                f"{context.symbol} is in a bullish regime with the close above the 20, 50, and 200 day averages. "
                "The weekly flow will only consider CALL structures while that stack holds."
            ),
            invalidation=f"Close back below the 20 day moving average ({context.ma20:.2f}) or roll the 20/50 day slopes negative.",
            catalyst_view="Deterministic lane only. Confirm the next event, earnings timing, and headline path before acting on the option screen.",
            review_confidence="high",
            countertrend_risk="high",
        )
    if context.trend_regime == "bearish":
        return StockReviewResult(
            direction="bearish",
            trend_regime=context.trend_regime,
            thesis_summary=(
                f"{context.symbol} is in a bearish regime with the close below the 20, 50, and 200 day averages. "
                "The weekly flow will only consider PUT structures while that stack holds."
            ),
            invalidation=f"Close back above the 20 day moving average ({context.ma20:.2f}) or recover positive 20/50 day slopes.",
            catalyst_view="Deterministic lane only. Confirm whether event timing or support levels undermine a straight bearish weekly thesis.",
            review_confidence="high",
            countertrend_risk="high",
        )
    return StockReviewResult(
        direction="no_trade",
        trend_regime=context.trend_regime,
        thesis_summary=(
            f"{context.symbol} does not have a clean stacked trend regime. "
            "The weekly directional flow skips mixed names rather than forcing a counter-trend contract."
        ),
        invalidation="Wait for either a bullish or bearish moving-average stack with matching short-term slopes.",
        catalyst_view="No directional weekly option should be surfaced until the regime resolves.",
        review_confidence="medium",
        countertrend_risk="high",
    )
