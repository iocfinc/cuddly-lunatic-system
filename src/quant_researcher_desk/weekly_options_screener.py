"""Broad weekly options screening workflow for the Quant Researcher Desk."""

from __future__ import annotations

import csv
import datetime as dt
import html
import json
import math
import os
import pathlib
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from quant_researcher_desk.fixture_options_market import (
    fixture_chain_expiry,
    fixture_company,
    fixture_daily_bars,
    fixture_expiries,
    fixture_market_snapshots,
    fixture_option_chain,
    fixture_plate_constituents,
    fixture_plate_list,
    fixture_spot,
)
from quant_researcher_desk.execution_recovery import (
    REASON_EMPTY_CHAIN,
    REASON_MISSING_DAILY_BARS,
    REASON_MISSING_CONTRACT_SNAPSHOT,
    REASON_MISSING_UNDERLYING_SNAPSHOT,
    REASON_MIXED_TREND_REGIME,
    REASON_NO_CONTRACT_MATCH,
    REASON_NO_EXPIRATIONS,
    REASON_PROVIDER_RATE_LIMITED,
    REASON_PROVIDER_UNREACHABLE,
    REASON_STOCK_REVIEW_FAILED,
    REASON_STOCK_REVIEW_NO_TRADE,
    SymbolExecutionError,
    SymbolSkip,
    count_skips_by_reason,
    make_symbol_error,
    representative_skip_details,
    summarize_skips,
    with_symbol_retry,
)
from quant_researcher_desk.moomoo_options_report import (
    OptionsReportError,
    QuoteClient,
    as_float,
    get_first,
    normalize_option_type,
)
from quant_researcher_desk.options_research import (
    build_option_contracts,
    black_scholes,
    classify_event_risk,
    EarningsContext,
    event_risk_score,
    event_risk_summary,
    get_earnings_context,
    valuation_view,
    implied_volatility,
    monte_carlo_option_price,
    price_option_with_engine,
    pricing_comparison_summary,
    pricing_engine_available,
    solve_implied_volatility_with_engine,
    years_to_expiry,
)
from quant_researcher_desk.reporting import ReportRenderError, render_html_file_to_pdf_with_chrome, write_native_pdf_report
from quant_researcher_desk.stock_context import StockContext, StockReviewResult, build_stock_context, fallback_stock_review


class WeeklyScreenQuoteClient(QuoteClient, Protocol):
    pass


@dataclass(frozen=True)
class WeeklyScreenRequest:
    market: str = "US"
    top_n: int = 10
    minimum_days_out: int = 5
    target_days_out: int = 7
    min_volume: int = 100
    min_open_interest: int = 100
    min_abs_delta: float = 0.20
    max_abs_delta: float = 0.60
    risk_free_rate: float = 0.04
    dividend_yield: float = 0.0
    historical_volatility: float = 0.25
    max_underlyings: int = 60
    monte_carlo_iterations: int = 4000
    monte_carlo_seed: int = 7
    pricing_engine: str = "legacy"
    shadow_compare: bool = False
    review_shortlist: bool = False
    analysis_mode: str = "stock-first"
    stock_review: bool = True
    stock_review_model: str = "gpt-5.5"


@dataclass(frozen=True)
class UnderlyingCandidate:
    symbol: str
    company: str
    source_plates: tuple[str, ...]


@dataclass(frozen=True)
class ScreenedOption:
    symbol: str
    company: str
    side: str
    option_code: str
    expiry: str
    days_to_expiry: int
    strike: float
    premium: float
    delta: float
    implied_volatility: float
    volume: int
    open_interest: int
    underlying_price: float
    black_scholes_fair_value: float
    monte_carlo_fair_value: float
    black_scholes_edge: float
    monte_carlo_edge: float
    model_edge_pct: float
    fair_value_gap_pct: float
    valuation_view: str
    liquidity_score: float
    expiry_fit_score: float
    iv_hv_adjustment: float
    directional_fit_score: float
    exit_quality_score: float
    valuation_context_score: float
    event_risk_score: float
    event_risk: str
    event_risk_detail: str
    event_within_holding_window: bool | None
    composite_score: float
    reason: str
    pricing_engine: str = "legacy"
    shadow_compare: bool = False
    quantlib_vs_legacy_diff: dict[str, Any] | None = None
    review_status: str = "Not Reviewed"
    review_flags: tuple[str, ...] = ()
    review_notes: str = ""
    trend_regime: str = "mixed"
    stock_direction: str = "no_trade"
    stock_review_summary: str = ""
    invalidation: str = ""
    alignment_status: str = "Unknown"
    catalyst_view: str = ""
    stock_review_confidence: str = ""
    countertrend_risk: str = ""


@dataclass(frozen=True)
class WeeklyScreenResult:
    generated_at: dt.datetime
    request: WeeklyScreenRequest
    universe: tuple[UnderlyingCandidate, ...]
    ranked_options: tuple[ScreenedOption, ...]
    gate_results: tuple[UnderlyingGateResult, ...]
    gate_summary: GateSummary
    skipped_underlyings: tuple[str, ...]
    skipped_symbols: tuple[SymbolSkip, ...]
    discovery_stats: dict[str, int]
    pricing_engine: str = "legacy"
    shadow_compare: bool = False
    reviewed_shortlist: bool = False
    review_summary: str | None = None
    reviewer_model: str | None = None


@dataclass(frozen=True)
class WeeklyReviewerConfig:
    enabled: bool = False
    reviewer_model: str | None = None
    reviewer_profile: str | None = "weekly_options_reviewer"


GATE_STAGE_UNIVERSE_DISCOVERY = "universe_discovery"
GATE_STAGE_STOCK_CONTEXT = "stock_context"
GATE_STAGE_WEEKLY_EXPIRY = "weekly_expiry"
GATE_STAGE_CONTRACT_QUALITY = "contract_quality"
GATE_STAGE_SHORTLIST_OUTCOME = "shortlist_outcome"

GATE_STAGES = (
    GATE_STAGE_UNIVERSE_DISCOVERY,
    GATE_STAGE_STOCK_CONTEXT,
    GATE_STAGE_WEEKLY_EXPIRY,
    GATE_STAGE_CONTRACT_QUALITY,
    GATE_STAGE_SHORTLIST_OUTCOME,
)

GATE_STATUS_PASSED = "passed"
GATE_STATUS_FAILED = "failed"


@dataclass(frozen=True)
class GateDecision:
    stage: str
    status: str
    reason_code: str
    detail: str


@dataclass(frozen=True)
class UnderlyingGateResult:
    symbol: str
    company: str
    source_plates: tuple[str, ...]
    decisions: tuple[GateDecision, ...]


@dataclass(frozen=True)
class GateStageSummary:
    stage: str
    passed: int
    failed: int


@dataclass(frozen=True)
class GateSummary:
    stage_rows: tuple[GateStageSummary, ...]
    pass_reasons: tuple[str, ...]
    fail_reasons: tuple[str, ...]


def _gate_pass(stage: str, reason_code: str, detail: str) -> GateDecision:
    return GateDecision(stage=stage, status=GATE_STATUS_PASSED, reason_code=reason_code, detail=detail)


def _gate_fail(stage: str, reason_code: str, detail: str) -> GateDecision:
    return GateDecision(stage=stage, status=GATE_STATUS_FAILED, reason_code=reason_code, detail=detail)


def _gate_stage_for_skip(skip: SymbolSkip) -> str:
    stage = str(skip.stage).strip().lower()
    if stage == "stock_context" or stage == "stock_review" or stage == "daily_bars":
        return GATE_STAGE_STOCK_CONTEXT
    if stage == "expirations" or stage == "expiry_selection":
        return GATE_STAGE_WEEKLY_EXPIRY
    if stage == "option_chain" or stage == "contract_snapshot" or stage == "contract_filters":
        return GATE_STAGE_CONTRACT_QUALITY
    return GATE_STAGE_SHORTLIST_OUTCOME


def _collect_representative_gate_reasons(
    gate_results: tuple[UnderlyingGateResult, ...],
    *,
    status: str,
    limit: int = 3,
) -> tuple[str, ...]:
    lines: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    for result in gate_results:
        for decision in result.decisions:
            if decision.status != status:
                continue
            key = (decision.stage, decision.reason_code, decision.detail)
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"{result.symbol} [{decision.stage}/{decision.reason_code}]: {decision.detail}")
            if len(lines) >= limit:
                return tuple(lines)
    return tuple(lines)


def _build_gate_summary(gate_results: tuple[UnderlyingGateResult, ...]) -> GateSummary:
    stage_rows: list[GateStageSummary] = []
    for stage in GATE_STAGES:
        passed = 0
        failed = 0
        for result in gate_results:
            for decision in result.decisions:
                if decision.stage != stage:
                    continue
                if decision.status == GATE_STATUS_PASSED:
                    passed += 1
                elif decision.status == GATE_STATUS_FAILED:
                    failed += 1
        stage_rows.append(GateStageSummary(stage=stage, passed=passed, failed=failed))
    return GateSummary(
        stage_rows=tuple(stage_rows),
        pass_reasons=_collect_representative_gate_reasons(gate_results, status=GATE_STATUS_PASSED),
        fail_reasons=_collect_representative_gate_reasons(gate_results, status=GATE_STATUS_FAILED),
    )


class FixtureWeeklyScreenProvider:
    """Deterministic provider for offline weekly-screen tests and dry runs."""

    def __init__(self, anchor_date: dt.date | None = None) -> None:
        self.anchor_date = anchor_date or dt.date(2026, 5, 26)

    def get_plate_list(self, market: str, plate_type: str = "ALL") -> list[dict[str, Any]]:
        return fixture_plate_list()

    def get_plate_constituents(self, plate_code: str) -> list[dict[str, Any]]:
        return fixture_plate_constituents(plate_code)

    def get_underlying_snapshot(self, symbol: str) -> dict[str, Any]:
        return {"code": symbol, "last_price": fixture_spot(symbol)}

    def get_option_expirations(self, symbol: str) -> list[str]:
        if symbol == "US.NOOPT":
            return []
        return fixture_expiries(self.anchor_date)

    def get_option_chain(self, symbol: str, expiry: str) -> list[dict[str, Any]]:
        return fixture_option_chain(symbol, expiry)

    def get_market_snapshots(self, codes: list[str]) -> list[dict[str, Any]]:
        return fixture_market_snapshots(codes)

    def get_daily_bars(self, symbol: str, count: int = 250) -> list[dict[str, Any]]:
        return fixture_daily_bars(symbol, count=count)

    def get_earnings_context(self, symbol: str) -> EarningsContext:
        if symbol.endswith("TSM"):
            return EarningsContext(
                next_date=(self.anchor_date + dt.timedelta(days=2)).isoformat(),
                phase="pre-earnings",
                summary="Fixture context: a scheduled event sits inside the weekly holding window.",
                risk_level="high",
                within_holding_window=True,
                source="fixture",
            )
        if symbol.endswith("AAPL"):
            return EarningsContext(
                next_date=(self.anchor_date + dt.timedelta(days=14)).isoformat(),
                phase="post-earnings drift",
                summary="Fixture context: no mapped event sits inside the intended weekly holding window.",
                risk_level="low",
                within_holding_window=False,
                source="fixture",
            )
        return EarningsContext(
            next_date=None,
            phase="unknown",
            summary="Fixture context: event timing is not mapped for this name.",
            risk_level="unknown",
            within_holding_window=None,
            source="fixture",
        )

    def close(self) -> None:
        return None


def load_weekly_reviewer_config(env: dict[str, str] | None = None) -> WeeklyReviewerConfig:
    values = env or os.environ
    enabled = values.get("WEEKLY_SHORTLIST_REVIEWER_ENABLED", "false").lower() == "true"
    reviewer_model = values.get("WEEKLY_SHORTLIST_REVIEWER_MODEL") or None
    reviewer_profile = values.get("WEEKLY_SHORTLIST_REVIEWER_PROFILE", "weekly_options_reviewer")
    return WeeklyReviewerConfig(
        enabled=enabled,
        reviewer_model=reviewer_model,
        reviewer_profile=reviewer_profile or None,
    )


def _normalized_market(value: str) -> str:
    market = value.strip().upper()
    if market != "US":
        raise OptionsReportError("Weekly options screener milestone is US-only.")
    return market


def _is_plate_constituent_rate_limit(exc: OptionsReportError) -> bool:
    message = str(exc).lower()
    return "high frequency" in message and "plate constituents" in message


def _select_weekly_expiry(expiries: list[str], now: dt.datetime, request: WeeklyScreenRequest) -> str:
    target = now.date() + dt.timedelta(days=request.target_days_out)
    eligible: list[tuple[dt.date, str]] = []
    for expiry in expiries:
        text = str(expiry).strip()
        if not text:
            continue
        try:
            expiry_date = dt.date.fromisoformat(text[:10])
        except ValueError:
            continue
        if (expiry_date - now.date()).days >= request.minimum_days_out:
            eligible.append((expiry_date, text[:10]))
    if not eligible:
        raise OptionsReportError(
            f"No option expirations at least {request.minimum_days_out} days out were returned by OpenD."
        )
    return min(
        eligible,
        key=lambda item: (
            abs((item[0] - target).days),
            0 if item[0] >= target else 1,
            item[0],
        ),
    )[1]


def discover_universe(
    client: WeeklyScreenQuoteClient,
    market: str,
    max_underlyings: int,
) -> tuple[list[UnderlyingCandidate], dict[str, int]]:
    plates = client.get_plate_list(market, "ALL")
    by_symbol: dict[str, UnderlyingCandidate] = {}
    raw_constituents = 0
    plate_rate_limit_hits = 0
    for plate in plates:
        if len(by_symbol) >= max_underlyings:
            break
        plate_code = str(get_first(plate, "code", default="")).strip()
        plate_name = str(get_first(plate, "plate_name", "stock_name", default=plate_code)).strip()
        if not plate_code:
            continue
        try:
            constituents = client.get_plate_constituents(plate_code)
        except OptionsReportError as exc:
            if _is_plate_constituent_rate_limit(exc) and by_symbol:
                plate_rate_limit_hits += 1
                break
            raise
        for row in constituents:
            raw_constituents += 1
            symbol = str(get_first(row, "code", "stock_code", default="")).strip()
            company = str(get_first(row, "stock_name", "name", default=symbol)).strip()
            if not symbol:
                continue
            existing = by_symbol.get(symbol)
            if existing is None:
                by_symbol[symbol] = UnderlyingCandidate(symbol=symbol, company=company, source_plates=(plate_name,))
            elif plate_name not in existing.source_plates:
                by_symbol[symbol] = UnderlyingCandidate(
                    symbol=existing.symbol,
                    company=existing.company,
                    source_plates=tuple(sorted((*existing.source_plates, plate_name))),
                )
    ordered = sorted(by_symbol.values(), key=lambda candidate: (candidate.symbol, candidate.company))
    return ordered[:max_underlyings], {
        "plates": len(plates),
        "raw_constituents": raw_constituents,
        "unique_underlyings": len(by_symbol),
        "plate_rate_limit_hits": plate_rate_limit_hits,
    }


def _normalized_analysis_mode(value: str) -> str:
    mode = value.strip().lower()
    if mode not in {"stock-first", "options-first"}:
        raise OptionsReportError(f"Unsupported weekly analysis mode: {value}")
    return mode


def _load_stock_context(client: WeeklyScreenQuoteClient, candidate: UnderlyingCandidate) -> StockContext:
    rows = with_symbol_retry(
        candidate.symbol,
        "daily_bars",
        lambda: client.get_daily_bars(candidate.symbol, count=250),
    )
    if not rows:
        raise make_symbol_error(
            candidate.symbol,
            "daily_bars",
            REASON_MISSING_DAILY_BARS,
            f"No daily bars returned for {candidate.symbol}.",
        )
    try:
        return build_stock_context(candidate.symbol, rows)
    except OptionsReportError as exc:
        raise make_symbol_error(
            candidate.symbol,
            "daily_bars",
            REASON_MISSING_DAILY_BARS,
            str(exc),
        ) from exc


def _should_abort_for_provider_pressure(
    skipped: list[SymbolSkip],
    *,
    processed_symbols: int,
    ranked_count: int,
) -> bool:
    if ranked_count > 0 or processed_symbols < 8:
        return False
    provider_skips = [
        skip for skip in skipped
        if skip.reason_code in {REASON_PROVIDER_RATE_LIMITED, REASON_PROVIDER_UNREACHABLE}
    ]
    if not provider_skips:
        return False
    consecutive_provider_skips = 0
    for skip in reversed(skipped):
        if skip.reason_code in {REASON_PROVIDER_RATE_LIMITED, REASON_PROVIDER_UNREACHABLE}:
            consecutive_provider_skips += 1
            continue
        break
    if consecutive_provider_skips >= 6:
        return True
    return len(provider_skips) / processed_symbols >= 0.7


def _provider_pressure_error(
    skipped: list[SymbolSkip],
    *,
    processed_symbols: int,
    universe_size: int,
) -> OptionsReportError:
    counts = count_skips_by_reason(skipped)
    provider_rate_limited = counts.get(REASON_PROVIDER_RATE_LIMITED, 0)
    provider_unreachable = counts.get(REASON_PROVIDER_UNREACHABLE, 0)
    return OptionsReportError(
        "Weekly screen aborted because OpenD transient provider failures dominated before any viable options were collected. "
        f"processed={processed_symbols}/{universe_size}; provider_rate_limited={provider_rate_limited}; "
        f"provider_unreachable={provider_unreachable}; skips={summarize_skips(skipped)}. "
        "Retry after the provider cooldown window or reduce max_underlyings."
    )


def _normalize_stock_review_result(value: StockReviewResult | dict[str, Any]) -> StockReviewResult:
    if isinstance(value, StockReviewResult):
        return value
    return StockReviewResult(
        direction=str(value.get("direction", "no_trade")),
        trend_regime=str(value.get("trend_regime", "mixed")),
        thesis_summary=str(value.get("thesis_summary", "")),
        invalidation=str(value.get("invalidation", "")),
        catalyst_view=str(value.get("catalyst_view", "")),
        review_confidence=str(value.get("review_confidence", "")),
        countertrend_risk=str(value.get("countertrend_risk", "")),
        model_used=str(value.get("model_used", "")) or None,
    )


def review_stock_candidate(
    candidate: UnderlyingCandidate,
    context: StockContext,
    request: WeeklyScreenRequest,
) -> StockReviewResult:
    del candidate, request
    return fallback_stock_review(context)


def _option_alignment_status(option_side: str, stock_direction: str) -> str:
    if stock_direction == "bullish":
        return "Aligned" if option_side == "CALL" else "Countertrend"
    if stock_direction == "bearish":
        return "Aligned" if option_side == "PUT" else "Countertrend"
    return "Unknown"


def _liquidity_score(volume: int, open_interest: int) -> float:
    raw = (math.log1p(max(volume, 0)) + 0.65 * math.log1p(max(open_interest, 0))) / 12.0
    return max(0.0, min(raw, 1.0))


def _expiry_fit_score(days_to_expiry: int, target_days_out: int) -> float:
    if target_days_out <= 0:
        return 1.0
    return max(0.0, 1.0 - abs(days_to_expiry - target_days_out) / max(target_days_out, 1))


def _iv_hv_adjustment(implied_volatility: float, historical_volatility: float) -> float:
    if historical_volatility <= 0:
        return 0.5
    if implied_volatility <= historical_volatility:
        return 1.0
    return max(0.25, historical_volatility / implied_volatility)


def _edge_score(edge_pct: float) -> float:
    return max(0.0, min(1.0, 0.5 + edge_pct))


def _delta_fit_score(delta: float, request: WeeklyScreenRequest) -> float:
    abs_delta = abs(delta)
    if abs_delta < request.min_abs_delta or abs_delta > request.max_abs_delta:
        return 0.0
    midpoint = (request.min_abs_delta + request.max_abs_delta) / 2
    half_band = max((request.max_abs_delta - request.min_abs_delta) / 2, 0.0001)
    distance = abs(abs_delta - midpoint) / half_band
    return max(0.0, 1.0 - 0.5 * distance)


def _directional_fit_score(option_side: str, stock_review: StockReviewResult | None, delta: float, request: WeeklyScreenRequest) -> float:
    if stock_review is None:
        return _delta_fit_score(delta, request)
    if _option_alignment_status(option_side, stock_review.direction) != "Aligned":
        return 0.0
    return _delta_fit_score(delta, request)


def _exit_quality_score(
    liquidity_score: float,
    expiry_fit_score: float,
    delta_fit_score: float,
) -> float:
    return liquidity_score * 0.55 + expiry_fit_score * 0.20 + delta_fit_score * 0.25


def _valuation_context_score(
    bs_edge_pct: float,
    mc_edge_pct: float,
    iv_hv_adjustment: float,
) -> float:
    return (
        _edge_score(bs_edge_pct) * 0.35
        + _edge_score(mc_edge_pct) * 0.35
        + iv_hv_adjustment * 0.30
    )


def _contract_passes_filters(contract: Any, request: WeeklyScreenRequest) -> bool:
    premium = float(contract.market_price)
    delta = abs(float(contract.delta or 0.0))
    return (
        premium > 0
        and contract.volume >= request.min_volume
        and contract.open_interest >= request.min_open_interest
        and request.min_abs_delta <= delta <= request.max_abs_delta
    )


def _score_contract(
    candidate: UnderlyingCandidate,
    contract: Any,
    underlying_price: float,
    now: dt.datetime,
    request: WeeklyScreenRequest,
    stock_review: StockReviewResult | None = None,
    earnings: EarningsContext | None = None,
    pricing_engines: dict[str, Any] | None = None,
) -> ScreenedOption:
    years = years_to_expiry(contract.expiry, now)
    volatility = contract.implied_volatility or solve_implied_volatility_with_engine(
        request.pricing_engine,
        contract.option_type,
        contract.market_price,
        underlying_price,
        contract.strike,
        years,
        request.risk_free_rate,
        request.dividend_yield,
        pricing_engines,
    )
    bs_result = price_option_with_engine(
        request.pricing_engine,
        contract.option_type,
        underlying_price,
        contract.strike,
        years,
        volatility,
        request.risk_free_rate,
        request.dividend_yield,
        pricing_engines,
    )
    bs = bs_result.theoretical_value
    mc = monte_carlo_option_price(
        contract.option_type,
        underlying_price,
        contract.strike,
        years,
        volatility,
        request.risk_free_rate,
        request.dividend_yield,
        iterations=request.monte_carlo_iterations,
        seed=request.monte_carlo_seed,
    )
    bs_edge = bs - contract.market_price
    mc_edge = mc - contract.market_price
    blended_edge_pct = ((bs + mc) / 2 - contract.market_price) / contract.market_price
    liquidity_score = _liquidity_score(contract.volume, contract.open_interest)
    days_to_expiry = max((dt.date.fromisoformat(contract.expiry[:10]) - now.date()).days, 0)
    expiry_fit_score = _expiry_fit_score(days_to_expiry, request.target_days_out)
    iv_hv_adjustment = _iv_hv_adjustment(volatility, request.historical_volatility)
    event_context = earnings or EarningsContext(
        next_date=None,
        phase="unknown",
        summary="No event context provider configured; keep timing risk explicit.",
    )
    directional_fit_score = _directional_fit_score(
        normalize_option_type(contract.option_type),
        stock_review,
        float(contract.delta or 0.0),
        request,
    )
    delta_fit_score = _delta_fit_score(float(contract.delta or 0.0), request)
    exit_quality_score = _exit_quality_score(liquidity_score, expiry_fit_score, delta_fit_score)
    valuation_context_score = _valuation_context_score(
        bs_edge / contract.market_price,
        mc_edge / contract.market_price,
        iv_hv_adjustment,
    )
    event_score = event_risk_score(event_context)
    event_risk = classify_event_risk(event_context)
    event_detail = event_risk_summary(event_context)
    composite_score = (
        directional_fit_score * 0.25
        + exit_quality_score * 0.35
        + valuation_context_score * 0.25
        + event_score * 0.15
    )
    shadow_summary = pricing_comparison_summary(
        active_engine=request.pricing_engine,
        option_type=contract.option_type,
        spot=underlying_price,
        strike=contract.strike,
        years=years,
        volatility=volatility,
        market_price=contract.market_price,
        risk_free_rate=request.risk_free_rate,
        dividend_yield=request.dividend_yield,
        pricing_engines=pricing_engines,
    ) if request.shadow_compare else None
    option_side = normalize_option_type(contract.option_type)
    alignment_status = _option_alignment_status(option_side, stock_review.direction if stock_review else "no_trade")
    reason = (
        f"{(stock_review.direction if stock_review else 'no_trade').replace('_', ' ').title()} stock context. "
        f"Exit quality reads {exit_quality_score:.2f} from {contract.volume:,} volume, {contract.open_interest:,} OI, and {days_to_expiry} DTE. "
        f"Valuation context is {blended_edge_pct:.1%} on a weekly horizon, with IV {volatility:.1%} versus "
        f"HV {request.historical_volatility:.1%}. Event risk is {event_risk}."
    )
    return ScreenedOption(
        symbol=candidate.symbol,
        company=candidate.company,
        side=option_side,
        option_code=contract.code,
        expiry=contract.expiry,
        days_to_expiry=days_to_expiry,
        strike=float(contract.strike),
        premium=float(contract.market_price),
        delta=float(contract.delta or 0.0),
        implied_volatility=float(volatility),
        volume=int(contract.volume),
        open_interest=int(contract.open_interest),
        underlying_price=float(underlying_price),
        black_scholes_fair_value=bs,
        monte_carlo_fair_value=mc,
        black_scholes_edge=bs_edge,
        monte_carlo_edge=mc_edge,
        model_edge_pct=blended_edge_pct,
        fair_value_gap_pct=blended_edge_pct,
        valuation_view=valuation_view(blended_edge_pct),
        liquidity_score=liquidity_score,
        expiry_fit_score=expiry_fit_score,
        iv_hv_adjustment=iv_hv_adjustment,
        directional_fit_score=directional_fit_score,
        exit_quality_score=exit_quality_score,
        valuation_context_score=valuation_context_score,
        event_risk_score=event_score,
        event_risk=event_risk,
        event_risk_detail=event_detail,
        event_within_holding_window=event_context.within_holding_window,
        composite_score=composite_score,
        reason=reason,
        pricing_engine=request.pricing_engine,
        shadow_compare=request.shadow_compare,
        quantlib_vs_legacy_diff=shadow_summary,
        trend_regime=stock_review.trend_regime if stock_review else "mixed",
        stock_direction=stock_review.direction if stock_review else "no_trade",
        stock_review_summary=stock_review.thesis_summary if stock_review else "",
        invalidation=stock_review.invalidation if stock_review else "",
        alignment_status=alignment_status,
        catalyst_view=stock_review.catalyst_view if stock_review else "",
        stock_review_confidence=stock_review.review_confidence if stock_review else "",
        countertrend_risk=stock_review.countertrend_risk if stock_review else "",
    )


def _review_shortlisted_option(option: ScreenedOption, request: WeeklyScreenRequest) -> ScreenedOption:
    flags: list[str] = []
    if option.alignment_status != "Aligned" and option.stock_direction in {"bullish", "bearish"}:
        flags.append("countertrend")
    spread_proxy = option.liquidity_score < 0.32 or option.volume < request.min_volume * 1.5
    if spread_proxy:
        flags.append("spread_proxy_wide")
    if option.fair_value_gap_pct <= -0.08:
        flags.append("rich_premium")
    if option.implied_volatility > request.historical_volatility * 1.35:
        flags.append("iv_above_hv")
    if abs(option.days_to_expiry - request.target_days_out) > 2:
        flags.append("expiry_fit_off_target")
    if not (request.min_abs_delta <= abs(option.delta) <= request.max_abs_delta):
        flags.append("delta_band_outside_target")
    if option.event_risk == "high":
        flags.append("event_inside_holding_window")
    elif option.event_risk == "unknown":
        flags.append("event_risk_unknown")
    shadow = option.quantlib_vs_legacy_diff or {}
    if option.shadow_compare and shadow.get("status") == "ok" and not shadow.get("within_tolerance", True):
        flags.append("quantlib_legacy_parity_gap")
    if abs(option.black_scholes_edge - option.monte_carlo_edge) > max(option.premium * 0.15, 0.35):
        flags.append("model_confidence_low")

    if any(flag in flags for flag in ("countertrend", "spread_proxy_wide", "delta_band_outside_target")):
        status = "Reject"
    elif any(flag in flags for flag in ("event_inside_holding_window", "event_risk_unknown", "quantlib_legacy_parity_gap", "model_confidence_low")):
        status = "Needs Human Review"
    elif any(flag in flags for flag in ("rich_premium", "iv_above_hv", "expiry_fit_off_target")):
        status = "Watch"
    else:
        status = "Candidate"

    if not flags:
        notes = "Liquidity, valuation, and model confidence all passed the deterministic reviewer lane."
    else:
        notes = "Deterministic reviewer flags: " + ", ".join(flag.replace("_", " ") for flag in flags) + "."
    return ScreenedOption(
        **{
            **option.__dict__,
            "review_status": status,
            "review_flags": tuple(flags),
            "review_notes": notes,
        }
    )


def _fallback_review_summary(result: WeeklyScreenResult) -> str:
    counts: dict[str, int] = {}
    for option in result.ranked_options:
        counts[option.review_status] = counts.get(option.review_status, 0) + 1
    status_line = ", ".join(f"{label}: {count}" for label, count in sorted(counts.items()))
    top_flags = sorted(
        {
            flag
            for option in result.ranked_options
            for flag in option.review_flags
        }
    )
    flag_line = ", ".join(flag.replace("_", " ") for flag in top_flags[:6]) if top_flags else "no major deterministic flags"
    return (
        "Shortlist reviewer ran after the stock-context gate. "
        f"Status mix: {status_line or 'no reviewed contracts'}. "
        f"Top flags: {flag_line}. "
        "Use this as a queue for deeper catalyst and spread review, not as a directional override."
    )


def _llm_review_prompt(result: WeeklyScreenResult) -> str:
    rows = shortlist_rows(result)
    return (
        "You are the portfolio-manager reviewer for a weekly options shortlist.\n\n"
        "Write 1 short paragraph. Explain which names deserve deeper follow-up and why. "
        "Use the deterministic review statuses and risk flags as the starting point. "
        "Do not give trading instructions.\n\n"
        f"Shortlist JSON:\n{json.dumps(rows, indent=2)}"
    )


def _summarize_review_with_llm(result: WeeklyScreenResult, config: WeeklyReviewerConfig) -> str:
    if not config.reviewer_model:
        return _fallback_review_summary(result)
    with tempfile.TemporaryDirectory(prefix="weekly-reviewer-") as tmp_dir:
        output_path = pathlib.Path(tmp_dir) / "review.txt"
        cmd = [
            "codex",
            "exec",
            "-m",
            config.reviewer_model,
            "-C",
            str(pathlib.Path(__file__).resolve().parents[2]),
            "-o",
            str(output_path),
            "-",
        ]
        if config.reviewer_profile:
            cmd[2:2] = ["-p", config.reviewer_profile]
        subprocess.run(
            cmd,
            input=_llm_review_prompt(result),
            text=True,
            capture_output=True,
            check=True,
            cwd=str(pathlib.Path(__file__).resolve().parents[2]),
            env=dict(os.environ),
        )
        return output_path.read_text(encoding="utf-8").strip() or _fallback_review_summary(result)


def build_weekly_options_screen(
    client: WeeklyScreenQuoteClient,
    request: WeeklyScreenRequest,
    now: dt.datetime | None = None,
    pricing_engines: dict[str, Any] | None = None,
    reviewer_config: WeeklyReviewerConfig | None = None,
) -> WeeklyScreenResult:
    generated_at = now or dt.datetime.now(dt.timezone.utc).astimezone()
    market = _normalized_market(request.market)
    analysis_mode = _normalized_analysis_mode(request.analysis_mode)
    if not pricing_engine_available(request.pricing_engine, pricing_engines):
        raise OptionsReportError(
            "Pricing engine 'quantlib' is unavailable. Install the QuantLib Python package before selecting it."
        )
    universe, stats = discover_universe(client, market, request.max_underlyings)
    ranked_options: list[ScreenedOption] = []
    skipped: list[SymbolSkip] = []
    with_target_expiry = 0
    gate_decisions_by_symbol: dict[str, list[GateDecision]] = {
        candidate.symbol: [
            _gate_pass(
                GATE_STAGE_UNIVERSE_DISCOVERY,
                "discovered_in_universe",
                f"Discovered from Moomoo plates: {', '.join(candidate.source_plates)}.",
            )
        ]
        for candidate in universe
    }
    contract_pass_counts: dict[str, int] = {}

    for processed_symbols, candidate in enumerate(universe, start=1):
        try:
            stock_context: StockContext | None = None
            stock_review: StockReviewResult | None = None
            aligned_side: str | None = None
            earnings = get_earnings_context(client, candidate.symbol)
            if analysis_mode == "stock-first":
                stock_context = _load_stock_context(client, candidate)
                if stock_context.trend_regime == "mixed":
                    raise make_symbol_error(
                        candidate.symbol,
                        "stock_context",
                        REASON_MIXED_TREND_REGIME,
                        f"{candidate.symbol} did not satisfy the bullish or bearish moving-average stack rules.",
                    )
                if request.stock_review:
                    try:
                        stock_review = _normalize_stock_review_result(review_stock_candidate(candidate, stock_context, request))
                    except Exception as exc:  # pragma: no cover - defensive seam for future live reviewer lane
                        raise make_symbol_error(
                            candidate.symbol,
                            "stock_review",
                            REASON_STOCK_REVIEW_FAILED,
                            str(exc),
                        ) from exc
                else:
                    stock_review = fallback_stock_review(stock_context)
                if stock_review.direction == "no_trade":
                    raise make_symbol_error(
                        candidate.symbol,
                        "stock_review",
                        REASON_STOCK_REVIEW_NO_TRADE,
                        f"Stock review blocked a directional weekly option for {candidate.symbol}.",
                    )
                aligned_side = "CALL" if stock_review.direction == "bullish" else "PUT"
                gate_decisions_by_symbol[candidate.symbol].append(
                    _gate_pass(
                        GATE_STAGE_STOCK_CONTEXT,
                        "stock_context_aligned",
                        f"Trend regime is {stock_context.trend_regime}; stock review aligned the weekly side to {aligned_side}.",
                    )
                )
            else:
                gate_decisions_by_symbol[candidate.symbol].append(
                    _gate_pass(
                        GATE_STAGE_STOCK_CONTEXT,
                        "stock_context_bypassed",
                        "Options-first mode bypassed the stock-context gate for this symbol.",
                    )
                )

            expiries = with_symbol_retry(
                candidate.symbol,
                "expirations",
                lambda: client.get_option_expirations(candidate.symbol),
            )
            if not expiries:
                raise make_symbol_error(
                    candidate.symbol,
                    "expirations",
                    REASON_NO_EXPIRATIONS,
                    f"No option expirations returned for {candidate.symbol}.",
                )
            expiry = _select_weekly_expiry(expiries, generated_at, request)
            with_target_expiry += 1
            gate_decisions_by_symbol[candidate.symbol].append(
                _gate_pass(
                    GATE_STAGE_WEEKLY_EXPIRY,
                    "weekly_expiry_found",
                    f"Selected weekly expiry {expiry} from {len(expiries)} returned expirations.",
                )
            )
            underlying = with_symbol_retry(
                candidate.symbol,
                "underlying_snapshot",
                lambda: client.get_underlying_snapshot(candidate.symbol),
            )
            underlying_price = as_float(get_first(underlying, "last_price", "cur_price", "price", default=None))
            if underlying_price is None:
                raise make_symbol_error(
                    candidate.symbol,
                    "underlying_snapshot",
                    REASON_MISSING_UNDERLYING_SNAPSHOT,
                    f"No underlying price available for {candidate.symbol}.",
                )

            chain_rows = with_symbol_retry(
                candidate.symbol,
                "option_chain",
                lambda: client.get_option_chain(candidate.symbol, expiry),
            )
            if not chain_rows:
                raise make_symbol_error(
                    candidate.symbol,
                    "option_chain",
                    REASON_EMPTY_CHAIN,
                    f"No option chain rows returned for {candidate.symbol} {expiry}.",
                )
            codes = [
                str(get_first(row, "code", default="")).strip()
                for row in chain_rows
                if str(get_first(row, "code", default="")).strip()
            ]
            if not codes:
                raise make_symbol_error(
                    candidate.symbol,
                    "contract_snapshot",
                    REASON_MISSING_CONTRACT_SNAPSHOT,
                    f"No option contract codes were returned for {candidate.symbol} {expiry}.",
                )
            snapshot_rows = with_symbol_retry(
                candidate.symbol,
                "contract_snapshot",
                lambda: client.get_market_snapshots(codes),
            ) if codes else []
            if codes and not snapshot_rows:
                raise make_symbol_error(
                    candidate.symbol,
                    "contract_snapshot",
                    REASON_MISSING_CONTRACT_SNAPSHOT,
                    f"No option contract snapshots returned for {candidate.symbol} {expiry}.",
                )
            contracts = build_option_contracts(chain_rows, snapshot_rows, expiry)
            if codes and not contracts:
                raise make_symbol_error(
                    candidate.symbol,
                    "contract_snapshot",
                    REASON_MISSING_CONTRACT_SNAPSHOT,
                    f"No option contract snapshots produced usable contracts for {candidate.symbol} {expiry}.",
                )
            liquid_contracts = [contract for contract in contracts if _contract_passes_filters(contract, request)]
            if analysis_mode == "stock-first" and aligned_side:
                liquid_contracts = [
                    contract for contract in liquid_contracts if normalize_option_type(contract.option_type) == aligned_side
                ]
            if not liquid_contracts:
                raise make_symbol_error(
                    candidate.symbol,
                    "contract_filters",
                    REASON_NO_CONTRACT_MATCH,
                    f"No matching contract survived the weekly liquidity and delta filters for {candidate.symbol} {expiry}.",
                )
            contract_pass_counts[candidate.symbol] = len(liquid_contracts)
            gate_decisions_by_symbol[candidate.symbol].append(
                _gate_pass(
                    GATE_STAGE_CONTRACT_QUALITY,
                    "contracts_survived_filters",
                    f"{len(liquid_contracts)} contracts survived the weekly premium, liquidity, delta, and side-alignment filters for {expiry}.",
                )
            )

            for contract in liquid_contracts:
                ranked_options.append(
                    _score_contract(
                        candidate,
                        contract,
                        underlying_price,
                        generated_at,
                        request,
                        stock_review,
                        earnings,
                        pricing_engines,
                    )
                )
        except SymbolExecutionError as exc:
            skipped.append(exc.skip)
            gate_decisions_by_symbol[candidate.symbol].append(
                _gate_fail(
                    _gate_stage_for_skip(exc.skip),
                    exc.reason_code,
                    exc.detail,
                )
            )
            if _should_abort_for_provider_pressure(
                skipped,
                processed_symbols=processed_symbols,
                ranked_count=len(ranked_options),
            ):
                raise _provider_pressure_error(
                    skipped,
                    processed_symbols=processed_symbols,
                    universe_size=len(universe),
                )
        except OptionsReportError as exc:
            skip = make_symbol_error(
                candidate.symbol,
                "expiry_selection",
                REASON_NO_EXPIRATIONS,
                str(exc),
            ).skip
            skipped.append(skip)
            gate_decisions_by_symbol[candidate.symbol].append(
                _gate_fail(
                    _gate_stage_for_skip(skip),
                    skip.reason_code,
                    skip.detail,
                )
            )
            if _should_abort_for_provider_pressure(
                skipped,
                processed_symbols=processed_symbols,
                ranked_count=len(ranked_options),
            ):
                raise _provider_pressure_error(
                    skipped,
                    processed_symbols=processed_symbols,
                    universe_size=len(universe),
                )

    stats["with_target_expiry"] = with_target_expiry
    stats.update(count_skips_by_reason(skipped))
    ranked_options.sort(
        key=lambda option: (
            -option.composite_score,
            -option.liquidity_score,
            -option.model_edge_pct,
            option.symbol,
            option.option_code,
        )
    )
    diversified: list[ScreenedOption] = []
    by_symbol: dict[str, list[ScreenedOption]] = {}
    for option in ranked_options:
        by_symbol.setdefault(option.symbol, []).append(option)
    while len(diversified) < request.top_n:
        added = False
        for symbol in sorted(by_symbol):
            contracts = by_symbol[symbol]
            if contracts:
                diversified.append(contracts.pop(0))
                added = True
                if len(diversified) >= request.top_n:
                    break
        if not added:
            break
    shortlisted_counts: dict[str, int] = {}
    for option in diversified:
        shortlisted_counts[option.symbol] = shortlisted_counts.get(option.symbol, 0) + 1
    skipped_by_symbol = {skip.symbol: skip for skip in skipped}
    gate_results = tuple(
        UnderlyingGateResult(
            symbol=candidate.symbol,
            company=candidate.company,
            source_plates=candidate.source_plates,
            decisions=tuple(
                [
                    *gate_decisions_by_symbol.get(candidate.symbol, []),
                    *(
                        [
                            _gate_pass(
                                GATE_STAGE_SHORTLIST_OUTCOME,
                                "shortlisted",
                                f"{shortlisted_counts[candidate.symbol]} contracts from {candidate.symbol} reached the published shortlist.",
                            )
                        ]
                        if candidate.symbol in shortlisted_counts
                        else [
                            _gate_fail(
                                GATE_STAGE_SHORTLIST_OUTCOME,
                                skipped_by_symbol[candidate.symbol].reason_code,
                                skipped_by_symbol[candidate.symbol].detail,
                            )
                        ]
                        if candidate.symbol in skipped_by_symbol
                        else [
                            _gate_fail(
                                GATE_STAGE_SHORTLIST_OUTCOME,
                                "ranked_out_after_diversification",
                                f"{contract_pass_counts.get(candidate.symbol, 0)} contracts passed quality filters, but none landed inside the published top {request.top_n}.",
                            )
                        ]
                    ),
                ]
            ),
        )
        for candidate in universe
    )
    gate_summary = _build_gate_summary(gate_results)
    if not diversified:
        provider_failures = sum(
            1
            for skip in skipped
            if skip.reason_code in {REASON_PROVIDER_RATE_LIMITED, REASON_PROVIDER_UNREACHABLE}
        )
        if provider_failures and provider_failures >= max(1, len(skipped) // 2):
            raise _provider_pressure_error(
                skipped,
                processed_symbols=len(universe),
                universe_size=len(universe),
            )
        raise OptionsReportError(
            "No viable weekly options remained after screening. "
            f"attempted={len(universe)}; skips={summarize_skips(skipped)}."
        )
    def _make_result(
        ranked: list[ScreenedOption] | tuple[ScreenedOption, ...],
        *,
        reviewed: bool,
        review_text: str | None,
    ) -> WeeklyScreenResult:
        return WeeklyScreenResult(
            generated_at=generated_at,
            request=request,
            universe=tuple(universe),
            ranked_options=tuple(ranked),
            gate_results=gate_results,
            gate_summary=gate_summary,
            skipped_underlyings=tuple(sorted({skip.symbol for skip in skipped})),
            skipped_symbols=tuple(skipped),
            discovery_stats=stats,
            pricing_engine=request.pricing_engine,
            shadow_compare=request.shadow_compare,
            reviewed_shortlist=reviewed,
            review_summary=review_text,
            reviewer_model=active_reviewer.reviewer_model if reviewed else None,
        )
    reviewed_shortlist = False
    review_summary: str | None = None
    active_reviewer = reviewer_config or load_weekly_reviewer_config()
    if request.review_shortlist:
        diversified = [_review_shortlisted_option(option, request) for option in diversified]
        reviewed_shortlist = True
        if active_reviewer.enabled:
            try:
                review_summary = _summarize_review_with_llm(_make_result(diversified, reviewed=True, review_text=None), active_reviewer)
            except (subprocess.SubprocessError, FileNotFoundError, OSError):
                review_summary = _fallback_review_summary(_make_result(diversified, reviewed=True, review_text=None))
        else:
            review_summary = _fallback_review_summary(_make_result(diversified, reviewed=True, review_text=None))
    return _make_result(diversified, reviewed=reviewed_shortlist, review_text=review_summary)


def shortlist_rows(result: WeeklyScreenResult) -> list[dict[str, Any]]:
    return [
        {
            "symbol": option.symbol,
            "side": option.side,
            "expiry": option.expiry,
            "strike": round(option.strike, 4),
            "premium": round(option.premium, 4),
            "delta": round(option.delta, 4),
            "iv": round(option.implied_volatility, 4),
            "volume": option.volume,
            "open_interest": option.open_interest,
            "black_scholes_fair_value": round(option.black_scholes_fair_value, 4),
            "monte_carlo_fair_value": round(option.monte_carlo_fair_value, 4),
            "model_edge": round(((option.black_scholes_fair_value + option.monte_carlo_fair_value) / 2) - option.premium, 4),
            "model_edge_pct": round(option.model_edge_pct, 4),
            "fair_value_gap_pct": round(option.fair_value_gap_pct, 4),
            "valuation_view": option.valuation_view,
            "pricing_engine": option.pricing_engine,
            "shadow_compare": option.shadow_compare,
            "trend_regime": option.trend_regime,
            "stock_direction": option.stock_direction,
            "stock_review_summary": option.stock_review_summary,
            "invalidation": option.invalidation,
            "alignment_status": option.alignment_status,
            "reason": option.reason,
            "directional_fit_score": round(option.directional_fit_score, 4),
            "exit_quality_score": round(option.exit_quality_score, 4),
            "valuation_context_score": round(option.valuation_context_score, 4),
            "event_risk_score": round(option.event_risk_score, 4),
            "event_risk": option.event_risk,
            "event_risk_detail": option.event_risk_detail,
            "review_status": option.review_status,
            "review_flags": ", ".join(option.review_flags),
        }
        for option in result.ranked_options
    ]


def _escape(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _format_number(value: float) -> str:
    return f"{value:,.2f}"


def _format_percent(value: float) -> str:
    return f"{value:.1%}"


def _theme_toggle_script() -> str:
    return """
<script>
(() => {
  const root = document.documentElement;
  const button = document.getElementById("theme-toggle");
  const label = document.getElementById("theme-toggle-label");
  const storageKey = "weekly-options-theme";
  const systemDark = window.matchMedia("(prefers-color-scheme: dark)");

  const applyTheme = (theme, persist) => {
    root.dataset.theme = theme;
    button?.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");
    if (label) {
      label.textContent = theme === "dark" ? "Switch to light" : "Switch to dark";
    }
    if (persist) {
      window.localStorage.setItem(storageKey, theme);
    }
  };

  const stored = window.localStorage.getItem(storageKey);
  applyTheme(stored || (systemDark.matches ? "dark" : "light"), false);

  button?.addEventListener("click", () => {
    applyTheme(root.dataset.theme === "dark" ? "light" : "dark", true);
  });

  systemDark.addEventListener?.("change", (event) => {
    if (!window.localStorage.getItem(storageKey)) {
      applyTheme(event.matches ? "dark" : "light", false);
    }
  });
})();
</script>
"""


def _weekly_screen_stylesheet() -> str:
    return """
:root {
  color-scheme: light dark;
  --page-bg: #f4efe8;
  --paper: rgba(255, 252, 247, 0.88);
  --paper-strong: #fff9f2;
  --ink: #171212;
  --muted: #5c5650;
  --line: #171212;
  --shadow: rgba(23, 18, 18, 0.16);
  --accent-purple: #7a3cff;
  --accent-orange: #ff7a1a;
  --accent-chartreuse: #cbff43;
  --accent-soft: rgba(122, 60, 255, 0.14);
  --danger-soft: rgba(255, 122, 26, 0.18);
  --success-soft: rgba(203, 255, 67, 0.24);
}
:root[data-theme="dark"] {
  --page-bg: #130f15;
  --paper: rgba(28, 21, 34, 0.9);
  --paper-strong: #1f1825;
  --ink: #f7f1ff;
  --muted: #c7bfd0;
  --line: #f7f1ff;
  --shadow: rgba(0, 0, 0, 0.34);
  --accent-soft: rgba(122, 60, 255, 0.24);
  --danger-soft: rgba(255, 122, 26, 0.24);
  --success-soft: rgba(203, 255, 67, 0.18);
}
@page {
  size: A4;
  margin: 14mm 12mm;
}
* { box-sizing: border-box; }
html, body { margin: 0; }
body {
  background:
    radial-gradient(circle at top left, rgba(122, 60, 255, 0.18), transparent 28%),
    radial-gradient(circle at top right, rgba(255, 122, 26, 0.16), transparent 26%),
    linear-gradient(180deg, var(--page-bg), color-mix(in srgb, var(--page-bg) 82%, #ffffff 18%));
  color: var(--ink);
  font-family: "Aptos", "Segoe UI", sans-serif;
  line-height: 1.5;
}
.page {
  margin: 0 auto;
  max-width: 1260px;
  padding: 28px;
}
.hero {
  background: var(--paper-strong);
  border: 3px solid var(--line);
  box-shadow: 14px 14px 0 var(--shadow);
  display: grid;
  gap: 18px;
  grid-template-columns: minmax(0, 2fr) minmax(280px, 1fr);
  padding: 24px;
}
.hero-copy {
  display: grid;
  gap: 12px;
}
.hero-kicker,
.section-kicker {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: var(--accent-chartreuse);
  border: 2px solid var(--line);
  color: #171212;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.12em;
  padding: 6px 10px;
  text-transform: uppercase;
  width: fit-content;
}
h1, h2, h3 {
  font-family: "Poppins", "Aptos Narrow", sans-serif;
  margin: 0;
}
h1 {
  font-size: clamp(2.9rem, 7vw, 5.5rem);
  letter-spacing: -0.04em;
  line-height: 0.9;
  max-width: 9ch;
  text-transform: uppercase;
}
.hero p {
  font-size: 1rem;
  margin: 0;
  max-width: 62ch;
}
.toolbar {
  align-items: start;
  display: grid;
  gap: 14px;
  justify-items: stretch;
}
.theme-toggle {
  align-items: center;
  background: var(--accent-purple);
  border: 3px solid var(--line);
  box-shadow: 8px 8px 0 var(--shadow);
  color: #fff;
  cursor: pointer;
  display: inline-flex;
  font: inherit;
  font-weight: 800;
  gap: 10px;
  justify-content: center;
  padding: 14px 16px;
  text-transform: uppercase;
}
.meta-grid,
.bento-grid,
.mini-grid {
  display: grid;
  gap: 18px;
}
.meta-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}
.bento-grid {
  grid-template-columns: repeat(12, minmax(0, 1fr));
  margin-top: 22px;
}
.mini-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.card {
  background: var(--paper);
  border: 3px solid var(--line);
  box-shadow: 10px 10px 0 var(--shadow);
  padding: 20px;
}
.card h2 {
  font-size: 1.6rem;
  line-height: 1;
  margin-top: 12px;
  text-transform: uppercase;
}
.card h3 {
  font-size: 0.95rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.card p, .card li {
  margin: 0;
}
.card ul {
  display: grid;
  gap: 10px;
  margin: 14px 0 0;
  padding-left: 18px;
}
.hero .meta-card,
.card .stat,
.card .pill,
.caption {
  border: 2px solid var(--line);
}
.meta-card {
  background: var(--paper);
  padding: 14px;
}
.meta-label,
.stat-label,
th {
  color: var(--muted);
  font-size: 0.78rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.meta-value,
.stat-value {
  display: block;
  font-size: 1.3rem;
  font-weight: 800;
  margin-top: 8px;
}
.stat {
  background: var(--paper-strong);
  padding: 14px;
}
.span-3 { grid-column: span 3; }
.span-4 { grid-column: span 4; }
.span-5 { grid-column: span 5; }
.span-6 { grid-column: span 6; }
.span-7 { grid-column: span 7; }
.span-8 { grid-column: span 8; }
.span-12 { grid-column: 1 / -1; }
.accent-purple { background: var(--accent-soft); }
.accent-orange { background: var(--danger-soft); }
.accent-chartreuse { background: var(--success-soft); }
.pill-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 16px;
}
.pill {
  background: var(--paper-strong);
  font-size: 0.9rem;
  font-weight: 700;
  padding: 8px 10px;
}
.caption {
  background: var(--paper-strong);
  display: inline-block;
  font-size: 0.85rem;
  font-weight: 700;
  margin-top: 16px;
  padding: 8px 10px;
}
table {
  border-collapse: collapse;
  margin-top: 16px;
  width: 100%;
}
th, td {
  border: 2px solid var(--line);
  padding: 10px 12px;
  text-align: left;
  vertical-align: top;
}
td {
  font-size: 0.94rem;
}
.mono {
  font-family: ui-monospace, "SFMono-Regular", Menlo, monospace;
}
.strong {
  font-weight: 800;
}
.muted {
  color: var(--muted);
}
.safe-copy {
  display: grid;
  gap: 12px;
}
@media print {
  body {
    background: var(--page-bg);
  }
  .page {
    max-width: none;
    padding: 0;
  }
  .theme-toggle {
    display: none;
  }
  .hero, .card {
    box-shadow: none;
    break-inside: avoid;
  }
}
@media (max-width: 980px) {
  .hero,
  .meta-grid,
  .mini-grid {
    grid-template-columns: 1fr;
  }
  .span-3,
  .span-4,
  .span-5,
  .span-6,
  .span-7,
  .span-8 {
    grid-column: 1 / -1;
  }
}
</style>
"""


def _render_html_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "<p>No rows available.</p>"
    headers = list(rows[0].keys())
    head = "".join(f"<th>{_escape(column.replace('_', ' '))}</th>" for column in headers)
    body = "".join(
        "<tr>"
        + "".join(f"<td>{_escape(row.get(column, ''))}</td>" for column in headers)
        + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _skip_reasons(result: WeeklyScreenResult) -> list[str]:
    if not result.skipped_symbols:
        return ["No symbols were skipped in this run."]
    return representative_skip_details(result.skipped_symbols, limit=6)


def _successful_symbols(result: WeeklyScreenResult) -> list[str]:
    return sorted({option.symbol for option in result.ranked_options})


def weekly_run_summary(result: WeeklyScreenResult) -> dict[str, Any]:
    skipped_by_reason = count_skips_by_reason(result.skipped_symbols)
    successful_symbols = _successful_symbols(result)
    return {
        "attempted_symbols": len(result.universe),
        "successful_symbols": successful_symbols,
        "successful_symbol_count": len(successful_symbols),
        "skipped_symbol_count": len(result.skipped_symbols),
        "skipped_by_reason": skipped_by_reason,
        "published_partial_output": bool(result.ranked_options) and bool(result.skipped_symbols),
    }


def gate_summary_rows(result: WeeklyScreenResult) -> list[dict[str, Any]]:
    return [
        {
            "stage": row.stage,
            "passed": row.passed,
            "failed": row.failed,
        }
        for row in result.gate_summary.stage_rows
    ]


def screen_report_sections(result: WeeklyScreenResult) -> list[dict[str, Any]]:
    rows = shortlist_rows(result)
    discovery_summary = (
        "The screener pulls plates first, deduplicates overlapping constituents, classifies stock trend regime from daily bars, then keeps only names with a weekly contract on the aligned side."
    )
    if result.discovery_stats.get("plate_rate_limit_hits", 0):
        discovery_summary += " OpenD rate-limited plate expansion during this run, so the screen continued with the already gathered partial universe."
    skip_counts = count_skips_by_reason(result.skipped_symbols)
    discovery_rows = [
        {"metric": "Plates", "value": result.discovery_stats.get("plates", 0)},
        {"metric": "Raw Constituents", "value": result.discovery_stats.get("raw_constituents", 0)},
        {"metric": "Unique Underlyings", "value": result.discovery_stats.get("unique_underlyings", 0)},
        {"metric": "Symbols Attempted", "value": len(result.universe)},
        {"metric": "With Weekly Expiry", "value": result.discovery_stats.get("with_target_expiry", 0)},
        {"metric": "Symbols With Ranked Contracts", "value": len(_successful_symbols(result))},
        {"metric": "Plate Rate Limit Hits", "value": result.discovery_stats.get("plate_rate_limit_hits", 0)},
        {"metric": "Shortlist Size", "value": len(result.ranked_options)},
    ]
    for reason_code, count in skip_counts.items():
        discovery_rows.append({"metric": f"Skipped: {reason_code}", "value": count})
    sections = [
        {
            "title": "What This Run Is",
            "content": (
                f"This {result.request.market} weekly options screen uses a stock-first methodology: discover names, classify bullish/bearish trend regime, "
                "reject mixed or no-trade stock context, then rank only aligned CALL or PUT contracts after premium, liquidity, and delta checks. "
                f"The active pricing engine is {result.pricing_engine}. It is a research queue for follow-up, not a trading signal."
            ),
        },
        {
            "title": "How Universe Discovery Works",
            "summary": discovery_summary,
            "table": discovery_rows,
        },
        {
            "title": "Why Some Names Were Skipped",
            "items": _skip_reasons(result),
        },
        {
            "title": "How Contracts Are Filtered",
            "items": [
                "Premium must be above zero, so the run avoids dead contracts and obvious stale prints.",
                f"Volume must be at least {result.request.min_volume:,} and open interest at least {result.request.min_open_interest:,}.",
                f"Absolute delta must stay between {result.request.min_abs_delta:.0%} and {result.request.max_abs_delta:.0%} so the shortlist avoids both lottery tails and near-stock proxies.",
                f"Target expiry is about {result.request.target_days_out} days out, with a minimum of {result.request.minimum_days_out} days.",
                "Bullish stock context can only surface CALLs, bearish stock context can only surface PUTs, and mixed context produces no directional candidate.",
            ],
        },
        {
            "title": "How Scoring Works",
            "summary": "Composite score blends stock alignment, resale-friendly exit quality, valuation context, and event policy rather than pretending any single model is enough.",
            "table": [
                {"component": "Directional Fit", "weight": "25%", "what_it_means": "Keeps the shortlist aligned to the stock-first lane and away from delta-band edge cases."},
                {"component": "Exit Quality", "weight": "35%", "what_it_means": "Rewards real volume, open interest, weekly DTE fit, and cleaner resale conditions."},
                {"component": "Valuation Context", "weight": "25%", "what_it_means": "Compares market premium against closed-form and simulated value while penalizing overheated IV."},
                {"component": "Event Risk", "weight": "15%", "what_it_means": "Flags and penalizes mapped or unknown catalyst timing without excluding the name by default."},
            ],
        },
        {
            "title": "Gate Trace",
            "summary": "Each symbol now carries a stable gate trail: discovered in the universe, evaluated for stock context, checked for weekly expiry, filtered for contract quality, then either published or dropped from the shortlist.",
            "table": gate_summary_rows(result),
            "items": [
                *result.gate_summary.pass_reasons,
                *result.gate_summary.fail_reasons,
            ] or ["No representative gate reasons were captured for this run."],
        },
        {
            "title": "Ranked Weekly Shortlist",
            "summary": "Use the CSV and JSON for machine workflows. Use the HTML and PDF to understand why the shortlist looks the way it does. Composite score is a review-priority signal, not a buy score.",
            "table": rows,
        },
    ]
    if result.reviewed_shortlist and result.review_summary:
        sections.append(
            {
                "title": "Shortlist Reviewer",
                "summary": result.review_summary,
                "table": [
                    {
                        "symbol": option.symbol,
                        "status": option.review_status,
                        "flags": ", ".join(option.review_flags) or "none",
                        "notes": option.review_notes,
                    }
                    for option in result.ranked_options
                ],
            }
        )
    sections.append(
        {
            "title": "How To Read The Output Safely",
            "items": [
                "Strike is the contract exercise reference price, not a target price for the stock.",
                "Fair Value Gap % compares blended model value against the current premium. Negative means the option looks rich versus the model.",
                "Valuation View translates the gap into Cheap, Near Fair, or Rich so a negative gap does not read like an endorsement.",
                "A higher score means the contract survived this screen better, not that the trade is right.",
                "Short-dated options can decay quickly even when the directional thesis is broadly correct.",
                "Model edge can disappear once spreads, catalyst timing, or intraday liquidity changes are considered.",
                "Treat the shortlist as the start of deeper work: event context, spreads, and thesis risk still need review.",
            ],
        }
    )
    return sections


def result_payload(result: WeeklyScreenResult) -> dict[str, Any]:
    return {
        "generated_at": result.generated_at.isoformat(),
        "market": result.request.market,
        "pricing_engine": result.pricing_engine,
        "shadow_compare": result.shadow_compare,
        "reviewed_shortlist": result.reviewed_shortlist,
        "review_summary": result.review_summary,
        "reviewer_model": result.reviewer_model,
        "request": asdict(result.request),
        "discovery_stats": result.discovery_stats,
        "run_summary": weekly_run_summary(result),
        "gate_results": [asdict(gate_result) for gate_result in result.gate_results],
        "gate_summary": asdict(result.gate_summary),
        "skipped_underlyings": list(result.skipped_underlyings),
        "skipped_symbols": [asdict(skip) for skip in result.skipped_symbols],
        "required_columns": list(shortlist_rows(result)[0].keys()) if result.ranked_options else [],
        "ranked_options": [asdict(option) for option in result.ranked_options],
    }


def render_shortlist_html(result: WeeklyScreenResult) -> str:
    rows = shortlist_rows(result)
    call_count = sum(1 for option in result.ranked_options if option.side == "CALL")
    put_count = sum(1 for option in result.ranked_options if option.side == "PUT")
    average_edge = (
        sum(option.model_edge_pct for option in result.ranked_options) / len(result.ranked_options)
        if result.ranked_options
        else 0.0
    )
    valuation_mix = {
        "Cheap": sum(1 for option in result.ranked_options if option.valuation_view == "Cheap"),
        "Near Fair": sum(1 for option in result.ranked_options if option.valuation_view == "Near Fair"),
        "Rich": sum(1 for option in result.ranked_options if option.valuation_view == "Rich"),
    }
    sections = screen_report_sections(result)
    section_by_title = {str(section["title"]): section for section in sections}
    discovery_rows = section_by_title["How Universe Discovery Works"]["table"]
    scoring_rows = section_by_title["How Scoring Works"]["table"]
    gate_trace_rows = section_by_title["Gate Trace"]["table"]
    shortlist_table = _render_html_table(rows)
    discovery_table = _render_html_table(discovery_rows)
    scoring_table = _render_html_table(scoring_rows)
    gate_trace_table = _render_html_table(gate_trace_rows)
    skipped_list = "".join(f"<li>{_escape(item)}</li>" for item in _skip_reasons(result))
    filter_list = "".join(f"<li>{_escape(item)}</li>" for item in section_by_title["How Contracts Are Filtered"]["items"])
    gate_trace_list = "".join(f"<li>{_escape(item)}</li>" for item in section_by_title["Gate Trace"]["items"])
    safety_list = "".join(f"<li>{_escape(item)}</li>" for item in section_by_title["How To Read The Output Safely"]["items"])
    reviewer_block = ""
    if "Shortlist Reviewer" in section_by_title:
        reviewer_block = (
            '<article class="card span-12 accent-orange">'
            '<span class="section-kicker">08</span>'
            "<h2>Shortlist Reviewer</h2>"
            f"<p>{_escape(section_by_title['Shortlist Reviewer']['summary'])}</p>"
            f"{_render_html_table(section_by_title['Shortlist Reviewer']['table'])}"
            "</article>"
        )
    generated_at = result.generated_at.strftime("%Y-%m-%d %H:%M:%S %Z").strip()
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_escape(result.request.market)} Weekly Options Screen</title>
  <style>{_weekly_screen_stylesheet()}</head>
<body>
  <main class="page">
    <header class="hero">
      <div class="hero-copy">
        <span class="hero-kicker">Quant Researcher Desk</span>
        <h1>{_escape(result.request.market)} Weekly Options Screen</h1>
        <p>This first-run report explains what the weekly screen just did, why some names fell out, and how the shortlist was ranked. The aim is comprehension first, not signal delivery.</p>
        <div class="meta-grid">
          <div class="meta-card"><span class="meta-label">Generated At</span><span class="meta-value">{_escape(generated_at)}</span></div>
          <div class="meta-card"><span class="meta-label">Weekly Window</span><span class="meta-value">{result.request.minimum_days_out}-{result.request.target_days_out} days</span></div>
          <div class="meta-card"><span class="meta-label">Artifacts</span><span class="meta-value">CSV + JSON + HTML + PDF</span></div>
        </div>
      </div>
      <div class="toolbar">
        <button id="theme-toggle" class="theme-toggle" type="button" aria-pressed="false">
          <span>Theme</span>
          <span id="theme-toggle-label">Switch to dark</span>
        </button>
        <div class="card accent-purple">
          <span class="section-kicker">Output Mix</span>
          <div class="mini-grid" style="margin-top: 14px;">
            <div class="stat"><span class="stat-label">Calls in shortlist</span><span class="stat-value">{call_count}</span></div>
            <div class="stat"><span class="stat-label">Puts in shortlist</span><span class="stat-value">{put_count}</span></div>
            <div class="stat"><span class="stat-label">Average model edge</span><span class="stat-value">{_format_percent(average_edge)}</span></div>
            <div class="stat"><span class="stat-label">Skipped symbols</span><span class="stat-value">{len(result.skipped_symbols)}</span></div>
          </div>
          <div class="pill-row">
            <span class="pill">Cheap {valuation_mix["Cheap"]}</span>
            <span class="pill">Near Fair {valuation_mix["Near Fair"]}</span>
            <span class="pill">Rich {valuation_mix["Rich"]}</span>
          </div>
        </div>
      </div>
    </header>

    <section class="bento-grid">
      <article class="card span-7 accent-purple">
        <span class="section-kicker">01</span>
        <h2>What This Run Is</h2>
        <p>{_escape(section_by_title["What This Run Is"]["content"])}</p>
        <div class="pill-row">
          <span class="pill">Universe discovery from Moomoo plates</span>
          <span class="pill">Weekly expiry selection</span>
          <span class="pill">Liquidity and delta gates</span>
          <span class="pill">{_escape(result.pricing_engine.title())} and Monte Carlo checks</span>
        </div>
      </article>

      <article class="card span-5 accent-chartreuse">
        <span class="section-kicker">02</span>
        <h2>How Universe Discovery Works</h2>
        <p>{_escape(section_by_title["How Universe Discovery Works"]["summary"])}</p>
        {discovery_table}
      </article>

      <article class="card span-4 accent-orange">
        <span class="section-kicker">03</span>
        <h2>Why Some Names Were Skipped</h2>
        <ul>{skipped_list}</ul>
        <span class="caption">Skipped names are normal. The point is to remove weak candidates early.</span>
      </article>

      <article class="card span-4">
        <span class="section-kicker">04</span>
        <h2>How Contracts Are Filtered</h2>
        <ul>{filter_list}</ul>
      </article>

      <article class="card span-4 accent-purple">
        <span class="section-kicker">05</span>
        <h2>How Scoring Works</h2>
        <p>{_escape(section_by_title["How Scoring Works"]["summary"])}</p>
        {scoring_table}
      </article>

      <article class="card span-12 accent-chartreuse">
        <span class="section-kicker">06</span>
        <h2>Gate Trace</h2>
        <p>{_escape(section_by_title["Gate Trace"]["summary"])}</p>
        {gate_trace_table}
        <ul>{gate_trace_list}</ul>
      </article>

      <article class="card span-12">
        <span class="section-kicker">07</span>
        <h2>Ranked Weekly Shortlist</h2>
        <p>{_escape(section_by_title["Ranked Weekly Shortlist"]["summary"])}</p>
        {shortlist_table}
      </article>

      {reviewer_block}

      <article class="card span-12 accent-chartreuse">
        <span class="section-kicker">09</span>
        <h2>How To Read The Output Safely</h2>
        <div class="safe-copy">
          <ul>{safety_list}</ul>
          <p class="caption strong">Read the machine artifacts for automation. Read this explainer before treating the shortlist as worth deeper review.</p>
        </div>
      </article>
    </section>
  </main>
  {_theme_toggle_script()}
</body>
</html>
"""


def write_shortlist_csv(path: pathlib.Path, result: WeeklyScreenResult) -> pathlib.Path:
    rows = shortlist_rows(result)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        if not rows:
            handle.write("")
            return path
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_shortlist_json(path: pathlib.Path, result: WeeklyScreenResult) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result_payload(result), indent=2), encoding="utf-8")
    return path


def write_shortlist_html(path: pathlib.Path, result: WeeklyScreenResult) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_shortlist_html(result), encoding="utf-8")
    return path


def write_shortlist_pdf(path: pathlib.Path, result: WeeklyScreenResult) -> pathlib.Path:
    html_path = write_shortlist_html(path.with_suffix(".html"), result)
    metadata = {
        "generated_at": result.generated_at.strftime("%Y-%m-%d %H:%M:%S %Z").strip(),
        "market": result.request.market,
        "shortlist_size": len(result.ranked_options),
    }
    sections = screen_report_sections(result)
    try:
        return render_html_file_to_pdf_with_chrome(html_path, path)
    except ReportRenderError:
        return write_native_pdf_report(
            "Weekly Options Shortlist",
            sections,
            metadata,
            path,
        )
    return path
