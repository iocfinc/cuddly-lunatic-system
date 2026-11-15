"""Shadow replay metrics for options finder changes."""

from __future__ import annotations

import math
from dataclasses import dataclass

TRADING_DAYS = 252


@dataclass(frozen=True)
class ReplayTrade:
    symbol: str
    option_code: str
    option_returns: tuple[float, ...]
    underlying_returns: tuple[float, ...]
    rejected_reason: str | None = None


@dataclass(frozen=True)
class ReplayMetrics:
    trade_count: int
    observation_count: int
    total_return: float
    baseline_return: float
    alpha: float
    sharpe: float
    hit_rate: float
    max_drawdown: float
    rejected_count: int
    rejection_reasons: tuple[str, ...]
    status: str


@dataclass(frozen=True)
class ReplayComparison:
    mode: str
    old: ReplayMetrics
    hardened: ReplayMetrics
    alpha_improvement: float
    sharpe_improvement: float


def _compound_return(returns: tuple[float, ...]) -> float:
    value = 1.0
    for item in returns:
        value *= 1.0 + item
    return value - 1.0


def _max_drawdown(returns: tuple[float, ...]) -> float:
    value = 1.0
    peak = 1.0
    drawdown = 0.0
    for item in returns:
        value *= 1.0 + item
        peak = max(peak, value)
        drawdown = min(drawdown, value / peak - 1.0)
    return drawdown


def _sharpe(excess_returns: tuple[float, ...]) -> float:
    if len(excess_returns) < 2:
        return 0.0
    mean = sum(excess_returns) / len(excess_returns)
    variance = sum((item - mean) ** 2 for item in excess_returns) / (len(excess_returns) - 1)
    stdev = math.sqrt(variance)
    if stdev == 0:
        return 0.0
    return mean / stdev * math.sqrt(TRADING_DAYS)


def replay_metrics(trades: tuple[ReplayTrade, ...] | list[ReplayTrade]) -> ReplayMetrics:
    accepted = tuple(trade for trade in trades if trade.rejected_reason is None)
    option_returns = tuple(item for trade in accepted for item in trade.option_returns)
    baseline_returns = tuple(item for trade in accepted for item in trade.underlying_returns)
    excess_returns = tuple(option - baseline for option, baseline in zip(option_returns, baseline_returns))
    rejection_reasons = tuple(
        reason
        for trade in trades
        for reason in ([trade.rejected_reason] if trade.rejected_reason is not None else [])
    )
    status = "ok" if len(option_returns) >= 2 else "insufficient_sample"
    total_return = _compound_return(option_returns) if option_returns else 0.0
    baseline_return = _compound_return(baseline_returns) if baseline_returns else 0.0
    hit_rate = (
        sum(1 for trade in accepted if _compound_return(trade.option_returns) > _compound_return(trade.underlying_returns))
        / len(accepted)
        if accepted
        else 0.0
    )
    return ReplayMetrics(
        trade_count=len(accepted),
        observation_count=len(option_returns),
        total_return=round(total_return, 6),
        baseline_return=round(baseline_return, 6),
        alpha=round(total_return - baseline_return, 6),
        sharpe=round(_sharpe(excess_returns), 6),
        hit_rate=round(hit_rate, 6),
        max_drawdown=round(_max_drawdown(option_returns), 6) if option_returns else 0.0,
        rejected_count=len(rejection_reasons),
        rejection_reasons=rejection_reasons,
        status=status,
    )


def compare_replay_sets(
    old_trades: tuple[ReplayTrade, ...] | list[ReplayTrade],
    hardened_trades: tuple[ReplayTrade, ...] | list[ReplayTrade],
    mode: str = "shadow_replay",
) -> ReplayComparison:
    old = replay_metrics(old_trades)
    hardened = replay_metrics(hardened_trades)
    return ReplayComparison(
        mode=mode,
        old=old,
        hardened=hardened,
        alpha_improvement=round(hardened.alpha - old.alpha, 6),
        sharpe_improvement=round(hardened.sharpe - old.sharpe, 6),
    )
