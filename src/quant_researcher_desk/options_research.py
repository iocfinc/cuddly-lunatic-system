"""Options pricing, scenario simulation, and research verdicts."""

from __future__ import annotations

import datetime as dt
import html
import importlib
import math
import random
from dataclasses import dataclass
from typing import Any, Protocol

from quant_researcher_desk.moomoo_options_report import (
    RISK_NOTE,
    OptionsReportError,
    as_float,
    as_int,
    extract_expiry,
    get_first,
    nearest_expiry,
    normalize_option_type,
)
from quant_researcher_desk.fixture_options_market import (
    fixture_chain_expiry,
    fixture_company,
    fixture_expiries,
    fixture_market_snapshots,
    fixture_option_chain,
    fixture_spot,
    monte_carlo_distribution_buckets,
)


TRADING_DAYS = 252
CALENDAR_DAYS = 365
PRICING_PARITY_TOLERANCES: dict[str, float] = {
    "theoretical_value": 0.05,
    "delta": 0.02,
    "gamma": 0.005,
    "theta": 0.02,
    "vega": 0.02,
    "rho": 0.02,
    "implied_volatility": 0.02,
}


class OptionsResearchProvider(Protocol):
    def get_underlying_snapshot(self, symbol: str) -> dict[str, Any]:
        ...

    def get_option_expirations(self, symbol: str) -> list[str]:
        ...

    def get_option_chain(self, symbol: str, expiry: str) -> list[dict[str, Any]]:
        ...

    def get_market_snapshots(self, codes: list[str]) -> list[dict[str, Any]]:
        ...


@dataclass(frozen=True)
class EarningsContext:
    next_date: str | None
    phase: str
    summary: str
    risk_level: str = "unknown"
    within_holding_window: bool | None = None
    source: str = "provider_optional"


@dataclass(frozen=True)
class OptionContract:
    code: str
    option_type: str
    strike: float
    expiry: str
    market_price: float
    implied_volatility: float | None
    delta: float | None
    open_interest: int
    volume: int


@dataclass(frozen=True)
class BlackScholesResult:
    theoretical_value: float
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float


@dataclass(frozen=True)
class ScenarioRow:
    price_shock_pct: float
    iv_shift_pct: float
    days_forward: int
    underlying_price: float
    option_value: float
    profit_loss: float


@dataclass(frozen=True)
class OptionsResearchRequest:
    symbol: str
    option_code: str | None = None
    option_type: str = "CALL"
    strike: float | None = None
    expiry: str | None = None
    rows: int = 5
    risk_free_rate: float = 0.04
    dividend_yield: float = 0.0
    historical_volatility: float = 0.35
    price_shocks: tuple[float, ...] = (-0.10, -0.05, 0.0, 0.05, 0.10)
    iv_shifts: tuple[float, ...] = (-0.10, 0.0, 0.10)
    days_forward: int = 7
    pricing_engine: str = "legacy"
    shadow_compare: bool = False


@dataclass(frozen=True)
class OptionsResearchReport:
    symbol: str
    generated_at: dt.datetime
    underlying_price: float
    contract: OptionContract
    model: BlackScholesResult
    model_edge: float
    model_edge_pct: float
    fair_value_gap_pct: float
    valuation_view: str
    implied_volatility_used: float
    historical_volatility: float
    scenario_rows: list[ScenarioRow]
    monte_carlo_distribution: list[dict[str, float | str]]
    smile_curve: list[dict[str, float | str]]
    years_to_expiry: float
    risk_free_rate: float
    dividend_yield: float
    black_scholes_curve: list[dict[str, float | str]]
    monte_carlo_paths: list[dict[str, Any]]
    verdict: str
    thesis: str
    risks: list[str]
    earnings: EarningsContext
    resale_thesis_summary: str = ""
    exit_quality_summary: str = ""
    event_risk_summary: str = ""
    pricing_engine: str = "legacy"
    shadow_compare: bool = False
    quantlib_vs_legacy_diff: dict[str, Any] | None = None


class FixtureOptionsResearchProvider:
    """Deterministic provider used for offline tests and cron dry-runs."""

    def __init__(self, anchor_date: dt.date | None = None) -> None:
        self.anchor_date = anchor_date or dt.date(2026, 5, 26)

    def get_underlying_snapshot(self, symbol: str) -> dict[str, Any]:
        return {"code": symbol, "last_price": fixture_spot(symbol)}

    def get_option_expirations(self, symbol: str) -> list[str]:
        if symbol == "US.TEST":
            return ["2026-05-15", "2026-06-19"]
        return fixture_expiries(self.anchor_date)

    def get_option_chain(self, symbol: str, expiry: str) -> list[dict[str, Any]]:
        if symbol == "US.TEST":
            return [
                {"code": f"{symbol}260515C100000", "option_type": "CALL", "strike_price": 100.0, "strike_time": expiry},
                {"code": f"{symbol}260515C105000", "option_type": "CALL", "strike_price": 105.0, "strike_time": expiry},
                {"code": f"{symbol}260515P095000", "option_type": "PUT", "strike_price": 95.0, "strike_time": expiry},
            ]
        return fixture_option_chain(symbol, expiry)

    def get_market_snapshots(self, codes: list[str]) -> list[dict[str, Any]]:
        if codes and all(code.startswith("US.TEST") for code in codes):
            rows = []
            for code in codes:
                if code.endswith("C100000"):
                    rows.append({"code": code, "last_price": 4.2, "implied_volatility": 0.32, "delta": 0.54, "open_interest": 1500, "volume": 420})
                elif code.endswith("C105000"):
                    rows.append({"code": code, "last_price": 2.1, "implied_volatility": 0.34, "delta": 0.34, "open_interest": 900, "volume": 240})
                else:
                    rows.append({"code": code, "last_price": 1.8, "implied_volatility": 0.36, "delta": -0.28, "open_interest": 700, "volume": 180})
            return rows
        return fixture_market_snapshots(codes)

    def get_earnings_context(self, symbol: str) -> EarningsContext:
        return EarningsContext(
            next_date=(self.anchor_date + dt.timedelta(days=3)).isoformat(),
            phase="pre-earnings",
            summary="Fixture context: earnings are inside the option window, so IV and gap risk require explicit sizing discipline.",
            risk_level="high",
            within_holding_window=True,
            source="fixture",
        )


def normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def normal_pdf(value: float) -> float:
    return math.exp(-0.5 * value * value) / math.sqrt(2.0 * math.pi)


def years_to_expiry(expiry: str, now: dt.datetime) -> float:
    expiry_date = dt.date.fromisoformat(expiry[:10])
    days = max((expiry_date - now.date()).days, 0)
    return max(days / CALENDAR_DAYS, 1 / CALENDAR_DAYS)


def _legacy_black_scholes(
    option_type: str,
    spot: float,
    strike: float,
    years: float,
    volatility: float,
    risk_free_rate: float = 0.04,
    dividend_yield: float = 0.0,
) -> BlackScholesResult:
    if spot <= 0 or strike <= 0 or years <= 0 or volatility <= 0:
        raise OptionsReportError("Black-Scholes inputs must be positive.")
    option_type = normalize_option_type(option_type)
    sqrt_t = math.sqrt(years)
    d1 = (math.log(spot / strike) + (risk_free_rate - dividend_yield + 0.5 * volatility * volatility) * years) / (volatility * sqrt_t)
    d2 = d1 - volatility * sqrt_t
    discount_q = math.exp(-dividend_yield * years)
    discount_r = math.exp(-risk_free_rate * years)

    if option_type == "CALL":
        value = spot * discount_q * normal_cdf(d1) - strike * discount_r * normal_cdf(d2)
        delta = discount_q * normal_cdf(d1)
        theta = (
            -(spot * discount_q * normal_pdf(d1) * volatility) / (2 * sqrt_t)
            - risk_free_rate * strike * discount_r * normal_cdf(d2)
            + dividend_yield * spot * discount_q * normal_cdf(d1)
        ) / CALENDAR_DAYS
        rho = strike * years * discount_r * normal_cdf(d2) / 100
    elif option_type == "PUT":
        value = strike * discount_r * normal_cdf(-d2) - spot * discount_q * normal_cdf(-d1)
        delta = -discount_q * normal_cdf(-d1)
        theta = (
            -(spot * discount_q * normal_pdf(d1) * volatility) / (2 * sqrt_t)
            + risk_free_rate * strike * discount_r * normal_cdf(-d2)
            - dividend_yield * spot * discount_q * normal_cdf(-d1)
        ) / CALENDAR_DAYS
        rho = -strike * years * discount_r * normal_cdf(-d2) / 100
    else:
        raise OptionsReportError(f"Unsupported option type: {option_type}")

    gamma = discount_q * normal_pdf(d1) / (spot * volatility * sqrt_t)
    vega = spot * discount_q * normal_pdf(d1) * sqrt_t / 100
    return BlackScholesResult(value, delta, gamma, theta, vega, rho)


def black_scholes(
    option_type: str,
    spot: float,
    strike: float,
    years: float,
    volatility: float,
    risk_free_rate: float = 0.04,
    dividend_yield: float = 0.0,
) -> BlackScholesResult:
    return _legacy_black_scholes(option_type, spot, strike, years, volatility, risk_free_rate, dividend_yield)


def _legacy_implied_volatility(
    option_type: str,
    market_price: float,
    spot: float,
    strike: float,
    years: float,
    risk_free_rate: float = 0.04,
    dividend_yield: float = 0.0,
    low: float = 0.0001,
    high: float = 5.0,
    tolerance: float = 0.0001,
    max_iterations: int = 100,
) -> float:
    if market_price <= 0:
        raise OptionsReportError("Market price must be positive to solve implied volatility.")
    for _ in range(max_iterations):
        mid = (low + high) / 2
        value = _legacy_black_scholes(option_type, spot, strike, years, mid, risk_free_rate, dividend_yield).theoretical_value
        if abs(value - market_price) <= tolerance:
            return mid
        if value > market_price:
            high = mid
        else:
            low = mid
    return (low + high) / 2


def implied_volatility(
    option_type: str,
    market_price: float,
    spot: float,
    strike: float,
    years: float,
    risk_free_rate: float = 0.04,
    dividend_yield: float = 0.0,
    low: float = 0.0001,
    high: float = 5.0,
    tolerance: float = 0.0001,
    max_iterations: int = 100,
) -> float:
    return _legacy_implied_volatility(
        option_type,
        market_price,
        spot,
        strike,
        years,
        risk_free_rate,
        dividend_yield,
        low,
        high,
        tolerance,
        max_iterations,
    )


def _load_quantlib() -> Any | None:
    try:
        return importlib.import_module("QuantLib")
    except ModuleNotFoundError:
        return None


def pricing_engine_available(pricing_engine: str, pricing_engines: dict[str, Any] | None = None) -> bool:
    if pricing_engines and pricing_engine in pricing_engines:
        checker = getattr(pricing_engines[pricing_engine], "is_available", None)
        return bool(checker() if callable(checker) else True)
    if pricing_engine == "legacy":
        return True
    if pricing_engine == "quantlib":
        return _load_quantlib() is not None
    return False


def _require_pricing_engine(pricing_engine: str, pricing_engines: dict[str, Any] | None = None) -> None:
    if pricing_engine_available(pricing_engine, pricing_engines):
        return
    if pricing_engine == "quantlib":
        raise OptionsReportError(
            "Pricing engine 'quantlib' is unavailable. Install the QuantLib Python package before selecting it."
        )
    raise OptionsReportError(f"Unsupported pricing engine: {pricing_engine}")


def _quantlib_black_scholes(
    option_type: str,
    spot: float,
    strike: float,
    years: float,
    volatility: float,
    risk_free_rate: float = 0.04,
    dividend_yield: float = 0.0,
) -> BlackScholesResult:
    ql = _load_quantlib()
    if ql is None:
        raise OptionsReportError(
            "Pricing engine 'quantlib' is unavailable. Install the QuantLib Python package before selecting it."
        )
    if spot <= 0 or strike <= 0 or years <= 0 or volatility <= 0:
        raise OptionsReportError("Black-Scholes inputs must be positive.")

    evaluation_date = ql.Date(1, ql.January, 2026)
    ql.Settings.instance().evaluationDate = evaluation_date
    maturity_days = max(int(round(years * CALENDAR_DAYS)), 1)
    exercise_date = evaluation_date + maturity_days
    option_flag = ql.Option.Call if normalize_option_type(option_type) == "CALL" else ql.Option.Put
    day_count = ql.Actual365Fixed()
    calendar = ql.NullCalendar()

    spot_handle = ql.QuoteHandle(ql.SimpleQuote(spot))
    dividend_handle = ql.YieldTermStructureHandle(ql.FlatForward(evaluation_date, dividend_yield, day_count))
    risk_handle = ql.YieldTermStructureHandle(ql.FlatForward(evaluation_date, risk_free_rate, day_count))
    vol_handle = ql.BlackVolTermStructureHandle(
        ql.BlackConstantVol(evaluation_date, calendar, volatility, day_count)
    )
    process = ql.BlackScholesMertonProcess(spot_handle, dividend_handle, risk_handle, vol_handle)
    option = ql.VanillaOption(ql.PlainVanillaPayoff(option_flag, strike), ql.EuropeanExercise(exercise_date))
    option.setPricingEngine(ql.AnalyticEuropeanEngine(process))
    return BlackScholesResult(
        theoretical_value=float(option.NPV()),
        delta=float(option.delta()),
        gamma=float(option.gamma()),
        theta=float(option.thetaPerDay()),
        vega=float(option.vega()) / 100.0,
        rho=float(option.rho()) / 100.0,
    )


def _quantlib_implied_volatility(
    option_type: str,
    market_price: float,
    spot: float,
    strike: float,
    years: float,
    risk_free_rate: float = 0.04,
    dividend_yield: float = 0.0,
    low: float = 0.0001,
    high: float = 5.0,
) -> float:
    ql = _load_quantlib()
    if ql is None:
        raise OptionsReportError(
            "Pricing engine 'quantlib' is unavailable. Install the QuantLib Python package before selecting it."
        )
    if market_price <= 0:
        raise OptionsReportError("Market price must be positive to solve implied volatility.")

    evaluation_date = ql.Date(1, ql.January, 2026)
    ql.Settings.instance().evaluationDate = evaluation_date
    maturity_days = max(int(round(years * CALENDAR_DAYS)), 1)
    exercise_date = evaluation_date + maturity_days
    option_flag = ql.Option.Call if normalize_option_type(option_type) == "CALL" else ql.Option.Put
    day_count = ql.Actual365Fixed()
    calendar = ql.NullCalendar()

    spot_handle = ql.QuoteHandle(ql.SimpleQuote(spot))
    dividend_handle = ql.YieldTermStructureHandle(ql.FlatForward(evaluation_date, dividend_yield, day_count))
    risk_handle = ql.YieldTermStructureHandle(ql.FlatForward(evaluation_date, risk_free_rate, day_count))
    vol_quote = ql.SimpleQuote(0.20)
    vol_handle = ql.BlackVolTermStructureHandle(
        ql.BlackConstantVol(evaluation_date, calendar, ql.QuoteHandle(vol_quote), day_count)
    )
    process = ql.BlackScholesMertonProcess(spot_handle, dividend_handle, risk_handle, vol_handle)
    option = ql.VanillaOption(ql.PlainVanillaPayoff(option_flag, strike), ql.EuropeanExercise(exercise_date))
    option.setPricingEngine(ql.AnalyticEuropeanEngine(process))
    try:
        return float(option.impliedVolatility(market_price, process, 1e-6, 100, low, high))
    except RuntimeError as exc:
        raise OptionsReportError(f"QuantLib could not solve implied volatility: {exc}") from exc


def price_option_with_engine(
    pricing_engine: str,
    option_type: str,
    spot: float,
    strike: float,
    years: float,
    volatility: float,
    risk_free_rate: float = 0.04,
    dividend_yield: float = 0.0,
    pricing_engines: dict[str, Any] | None = None,
) -> BlackScholesResult:
    if pricing_engines and pricing_engine in pricing_engines:
        return pricing_engines[pricing_engine].price(
            option_type,
            spot,
            strike,
            years,
            volatility,
            risk_free_rate,
            dividend_yield,
        )
    if pricing_engine == "legacy":
        return _legacy_black_scholes(option_type, spot, strike, years, volatility, risk_free_rate, dividend_yield)
    if pricing_engine == "quantlib":
        return _quantlib_black_scholes(option_type, spot, strike, years, volatility, risk_free_rate, dividend_yield)
    raise OptionsReportError(f"Unsupported pricing engine: {pricing_engine}")


def solve_implied_volatility_with_engine(
    pricing_engine: str,
    option_type: str,
    market_price: float,
    spot: float,
    strike: float,
    years: float,
    risk_free_rate: float = 0.04,
    dividend_yield: float = 0.0,
    pricing_engines: dict[str, Any] | None = None,
) -> float:
    if pricing_engines and pricing_engine in pricing_engines:
        return pricing_engines[pricing_engine].solve_implied_volatility(
            option_type,
            market_price,
            spot,
            strike,
            years,
            risk_free_rate,
            dividend_yield,
        )
    if pricing_engine == "legacy":
        return _legacy_implied_volatility(
            option_type,
            market_price,
            spot,
            strike,
            years,
            risk_free_rate,
            dividend_yield,
        )
    if pricing_engine == "quantlib":
        return _quantlib_implied_volatility(
            option_type,
            market_price,
            spot,
            strike,
            years,
            risk_free_rate,
            dividend_yield,
        )
    raise OptionsReportError(f"Unsupported pricing engine: {pricing_engine}")


def pricing_comparison_summary(
    *,
    active_engine: str,
    option_type: str,
    spot: float,
    strike: float,
    years: float,
    volatility: float,
    market_price: float,
    risk_free_rate: float,
    dividend_yield: float,
    pricing_engines: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    comparison_engine = "legacy" if active_engine == "quantlib" else "quantlib"
    summary: dict[str, Any] = {
        "active_engine": active_engine,
        "comparison_engine": comparison_engine,
    }
    if not pricing_engine_available(comparison_engine, pricing_engines):
        summary.update(
            {
                "status": "unavailable",
                "within_tolerance": False,
                "reason": "comparison engine unavailable in this environment",
            }
        )
        return summary

    active_model = price_option_with_engine(
        active_engine,
        option_type,
        spot,
        strike,
        years,
        volatility,
        risk_free_rate,
        dividend_yield,
        pricing_engines,
    )
    comparison_model = price_option_with_engine(
        comparison_engine,
        option_type,
        spot,
        strike,
        years,
        volatility,
        risk_free_rate,
        dividend_yield,
        pricing_engines,
    )
    active_iv = solve_implied_volatility_with_engine(
        active_engine,
        option_type,
        market_price,
        spot,
        strike,
        years,
        risk_free_rate,
        dividend_yield,
        pricing_engines,
    )
    comparison_iv = solve_implied_volatility_with_engine(
        comparison_engine,
        option_type,
        market_price,
        spot,
        strike,
        years,
        risk_free_rate,
        dividend_yield,
        pricing_engines,
    )
    active_values = {
        "theoretical_value": active_model.theoretical_value,
        "delta": active_model.delta,
        "gamma": active_model.gamma,
        "theta": active_model.theta,
        "vega": active_model.vega,
        "rho": active_model.rho,
        "implied_volatility": active_iv,
    }
    comparison_values = {
        "theoretical_value": comparison_model.theoretical_value,
        "delta": comparison_model.delta,
        "gamma": comparison_model.gamma,
        "theta": comparison_model.theta,
        "vega": comparison_model.vega,
        "rho": comparison_model.rho,
        "implied_volatility": comparison_iv,
    }
    diffs = {
        metric: abs(float(active_values[metric]) - float(comparison_values[metric]))
        for metric in active_values
    }
    failed_metrics = [
        metric for metric, tolerance in PRICING_PARITY_TOLERANCES.items() if diffs[metric] > tolerance
    ]
    summary.update(
        {
            "status": "ok",
            "within_tolerance": not failed_metrics,
            "tolerance_failures": failed_metrics,
            "tolerances": dict(PRICING_PARITY_TOLERANCES),
            "active_values": active_values,
            "comparison_values": comparison_values,
            "diffs": diffs,
        }
    )
    return summary


def monte_carlo_option_price(
    option_type: str,
    spot: float,
    strike: float,
    years: float,
    volatility: float,
    risk_free_rate: float = 0.04,
    dividend_yield: float = 0.0,
    iterations: int = 5000,
    seed: int = 7,
) -> float:
    if spot <= 0 or strike <= 0 or years <= 0 or volatility <= 0:
        raise OptionsReportError("Monte Carlo inputs must be positive.")
    if iterations <= 0:
        raise OptionsReportError("Monte Carlo iterations must be positive.")

    normalized_type = normalize_option_type(option_type)
    drift = (risk_free_rate - dividend_yield - 0.5 * volatility * volatility) * years
    sigma = volatility * math.sqrt(years)
    rng = random.Random(seed)
    payoff_sum = 0.0

    for _ in range(iterations):
        terminal_spot = spot * math.exp(drift + sigma * rng.gauss(0.0, 1.0))
        if normalized_type == "CALL":
            payoff = max(terminal_spot - strike, 0.0)
        elif normalized_type == "PUT":
            payoff = max(strike - terminal_spot, 0.0)
        else:
            raise OptionsReportError(f"Unsupported option type: {option_type}")
        payoff_sum += payoff

    return math.exp(-risk_free_rate * years) * (payoff_sum / iterations)


def monte_carlo_option_distribution(
    option_type: str,
    spot: float,
    strike: float,
    years: float,
    volatility: float,
    risk_free_rate: float = 0.04,
    dividend_yield: float = 0.0,
    iterations: int = 5000,
    seed: int = 7,
) -> list[float]:
    if spot <= 0 or strike <= 0 or years <= 0 or volatility <= 0:
        raise OptionsReportError("Monte Carlo inputs must be positive.")
    normalized_type = normalize_option_type(option_type)
    drift = (risk_free_rate - dividend_yield - 0.5 * volatility * volatility) * years
    sigma = volatility * math.sqrt(years)
    rng = random.Random(seed)
    values: list[float] = []
    for _ in range(iterations):
        terminal_spot = spot * math.exp(drift + sigma * rng.gauss(0.0, 1.0))
        if normalized_type == "CALL":
            payoff = max(terminal_spot - strike, 0.0)
        else:
            payoff = max(strike - terminal_spot, 0.0)
        values.append(math.exp(-risk_free_rate * years) * payoff)
    return values


def build_option_contracts(chain_rows: list[dict[str, Any]], snapshot_rows: list[dict[str, Any]], expiry: str) -> list[OptionContract]:
    snapshots_by_code = {str(row.get("code", "")): row for row in snapshot_rows}
    contracts: list[OptionContract] = []
    for row in chain_rows:
        code = str(get_first(row, "code", "stock", default="")).strip()
        if not code:
            continue
        merged = {**row, **snapshots_by_code.get(code, {})}
        option_type = normalize_option_type(get_first(merged, "option_type", "type", default=""))
        strike = as_float(get_first(merged, "strike_price", "strike", default=None))
        market_price = as_float(get_first(merged, "last_price", "cur_price", "price", default=None))
        if option_type not in {"CALL", "PUT"} or strike is None or market_price is None:
            continue
        contracts.append(
            OptionContract(
                code=code,
                option_type=option_type,
                strike=strike,
                expiry=extract_expiry(merged) or expiry,
                market_price=market_price,
                implied_volatility=as_float(get_first(merged, "implied_volatility", "implied_vol", "iv", default=None)),
                delta=as_float(get_first(merged, "delta", "option_delta", default=None)),
                open_interest=as_int(get_first(merged, "open_interest", "option_open_interest", default=0)),
                volume=as_int(get_first(merged, "volume", "option_volume", default=0)),
            )
        )
    return contracts


def select_contract(contracts: list[OptionContract], request: OptionsResearchRequest, underlying_price: float) -> OptionContract:
    if request.option_code:
        for contract in contracts:
            if contract.code == request.option_code:
                return contract
        raise OptionsReportError(f"Requested option code was not found: {request.option_code}")

    option_type = normalize_option_type(request.option_type)
    matching = [contract for contract in contracts if contract.option_type == option_type]
    if request.strike is not None:
        matching = [contract for contract in matching if abs(contract.strike - request.strike) < 0.0001]
    if not matching:
        raise OptionsReportError("No contract matched the requested option filters.")
    return sorted(matching, key=lambda contract: (-contract.volume, -contract.open_interest, abs(contract.strike - underlying_price)))[0]


def get_earnings_context(provider: OptionsResearchProvider, symbol: str) -> EarningsContext:
    getter = getattr(provider, "get_earnings_context", None)
    if callable(getter):
        context = getter(symbol)
        if isinstance(context, EarningsContext):
            return context
    return EarningsContext(
        next_date=None,
        phase="unknown",
        summary="No earnings context provider configured; treat event timing as an explicit uncertainty.",
        risk_level="unknown",
        within_holding_window=None,
        source="provider_optional",
    )


def classify_event_risk(context: EarningsContext) -> str:
    level = context.risk_level.strip().lower()
    if level in {"low", "medium", "high", "unknown"}:
        return level
    if context.within_holding_window is True:
        return "high"
    if context.within_holding_window is False:
        return "low"
    return "unknown"


def event_risk_score(context: EarningsContext) -> float:
    risk = classify_event_risk(context)
    if risk == "low":
        return 1.0
    if risk == "medium":
        return 0.65
    if risk == "high":
        return 0.25
    return 0.50


def event_risk_summary(context: EarningsContext) -> str:
    risk = classify_event_risk(context)
    if risk == "high":
        return "A scheduled catalyst sits inside the intended holding window, so keep the contract in lane but treat gap risk as a real resale penalty."
    if risk == "medium":
        return "A nearby catalyst is mapped, but it does not cleanly sit inside the base holding window; keep sizing and exit timing conservative."
    if risk == "low":
        return "No mapped catalyst sits inside the intended holding window, so the contract reads cleaner from an event-timing standpoint."
    return "Event timing is unknown, so the lane stays open but carries an explicit caution until catalyst context is verified."


def exit_quality_summary(contract: OptionContract, *, target_days_out: int, days_to_expiry: int, delta_band: tuple[float, float]) -> str:
    min_delta, max_delta = delta_band
    abs_delta = abs(contract.delta or 0.0)
    liquidity = "strong" if contract.volume >= 200 and contract.open_interest >= 200 else "borderline"
    dte_note = "on target" if abs(days_to_expiry - target_days_out) <= 2 else "off target"
    if abs_delta < min_delta:
        delta_note = "too low-delta for a clean resale thesis"
    elif abs_delta > max_delta:
        delta_note = "too deep in the money and drifting toward stock-proxy behavior"
    else:
        delta_note = "inside the intended delta band"
    return (
        f"Exit quality reads {liquidity}: {contract.volume:,} volume, {contract.open_interest:,} open interest, "
        f"{days_to_expiry} DTE ({dte_note}), and delta {abs_delta:.2f} is {delta_note}."
    )


def resale_thesis_summary(
    contract: OptionContract,
    *,
    valuation: str,
    model_edge_pct: float,
    event_summary: str,
) -> str:
    return (
        f"The v1 lane is contract resale, not exercise into stock. {contract.code} is a {contract.option_type.lower()} "
        f"candidate because the premium reads {valuation.lower()} versus model context ({model_edge_pct:.1%} gap), "
        f"so the thesis is to monetize repricing and directional follow-through before expiry. {event_summary}"
    )


def valuation_view(fair_value_gap_pct: float) -> str:
    if fair_value_gap_pct >= 0.05:
        return "Cheap"
    if fair_value_gap_pct <= -0.05:
        return "Rich"
    return "Near Fair"


def build_smile_curve(chain_rows: list[dict[str, Any]], snapshot_rows: list[dict[str, Any]], expiry: str) -> list[dict[str, float | str]]:
    rows = []
    for contract in build_option_contracts(chain_rows, snapshot_rows, expiry):
        if contract.implied_volatility is None:
            continue
        rows.append(
            {
                "label": f"{contract.option_type} {contract.strike:.0f}",
                "strike": contract.strike,
                "value": float(contract.implied_volatility),
                "side": contract.option_type,
            }
        )
    rows.sort(key=lambda row: (str(row["side"]), float(row["strike"])))
    return rows


def build_black_scholes_curve(
    contract: OptionContract,
    underlying_price: float,
    volatility: float,
    years: float,
    request: OptionsResearchRequest,
) -> list[dict[str, float | str]]:
    rows: list[dict[str, float | str]] = []
    for price_shock in (-0.15, -0.10, -0.05, 0.0, 0.05, 0.10, 0.15):
        scenario_spot = underlying_price * (1 + price_shock)
        value = black_scholes(
            contract.option_type,
            scenario_spot,
            contract.strike,
            years,
            volatility,
            request.risk_free_rate,
            request.dividend_yield,
        ).theoretical_value
        rows.append({"label": format_money(scenario_spot), "value": round(value, 4)})
    return rows


def build_monte_carlo_sample_paths(
    underlying_price: float,
    volatility: float,
    years: float,
    request: OptionsResearchRequest,
    *,
    sample_paths: int = 5,
    seed: int = 17,
) -> list[dict[str, Any]]:
    if underlying_price <= 0 or volatility <= 0 or years <= 0:
        return []
    total_days = max(int(round(years * CALENDAR_DAYS)), 1)
    steps = min(max(total_days, 6), 12)
    delta_t = years / steps
    drift = (request.risk_free_rate - request.dividend_yield - 0.5 * volatility * volatility) * delta_t
    sigma = volatility * math.sqrt(delta_t)
    rng = random.Random(seed)
    series: list[dict[str, Any]] = []
    for index in range(sample_paths):
        current = underlying_price
        rows = [{"label": "0d", "value": round(current, 4)}]
        for step in range(1, steps + 1):
            current = current * math.exp(drift + sigma * rng.gauss(0.0, 1.0))
            day_label = int(round(step * total_days / steps))
            rows.append({"label": f"{day_label}d", "value": round(current, 4)})
        series.append({"label": f"Path {index + 1}", "rows": rows})
    return series


def build_scenarios(
    contract: OptionContract,
    underlying_price: float,
    volatility: float,
    years: float,
    request: OptionsResearchRequest,
) -> list[ScenarioRow]:
    rows: list[ScenarioRow] = []
    forward_years = max(years - request.days_forward / CALENDAR_DAYS, 1 / CALENDAR_DAYS)
    for price_shock in request.price_shocks:
        for iv_shift in request.iv_shifts:
            scenario_spot = underlying_price * (1 + price_shock)
            scenario_vol = max(volatility + iv_shift, 0.0001)
            value = black_scholes(
                contract.option_type,
                scenario_spot,
                contract.strike,
                forward_years,
                scenario_vol,
                request.risk_free_rate,
                request.dividend_yield,
            ).theoretical_value
            rows.append(
                ScenarioRow(
                    price_shock_pct=price_shock,
                    iv_shift_pct=iv_shift,
                    days_forward=request.days_forward,
                    underlying_price=scenario_spot,
                    option_value=value,
                    profit_loss=value - contract.market_price,
                )
            )
    return rows


def research_verdict(
    contract: OptionContract,
    model_edge_pct: float,
    volatility: float,
    historical_volatility: float,
    earnings: EarningsContext,
) -> tuple[str, str, list[str]]:
    risks: list[str] = []
    if contract.volume < 50 or contract.open_interest < 100:
        risks.append("Liquidity is thin; volume or open interest is below the minimum research threshold.")
    if volatility > historical_volatility * 1.35:
        risks.append("Implied volatility is materially above historical volatility; premium may already price in the catalyst.")
    if abs(contract.delta or 0.0) < 0.20:
        risks.append("Delta is low, so the contract may require a large underlying move before thesis expression is meaningful.")
    if classify_event_risk(earnings) == "high":
        risks.append("A mapped catalyst falls inside the likely holding window, so resale timing matters as much as valuation.")
    elif classify_event_risk(earnings) == "unknown":
        risks.append("Catalyst timing is unknown, so the report keeps event risk explicit instead of assuming a clean window.")

    if risks and model_edge_pct < 0.10:
        verdict = "Reject"
    elif model_edge_pct >= 0.15 and not risks:
        verdict = "Research Candidate"
    else:
        verdict = "Watchlist"

    thesis = (
        f"{contract.code} screens as {verdict}. Fair value is {model_edge_pct:.1%} versus the observed premium, "
        f"with IV at {volatility:.1%} against a {historical_volatility:.1%} HV baseline. "
        "The read-through is valuation discipline first: premium, liquidity, and event timing matter more than direction alone."
    )
    if not risks:
        risks.append("No blocking quantitative risk was detected, but sizing and event timing still require human review.")
    return verdict, thesis, risks


def build_options_research_report(
    provider: OptionsResearchProvider,
    request: OptionsResearchRequest,
    now: dt.datetime | None = None,
    pricing_engines: dict[str, Any] | None = None,
) -> OptionsResearchReport:
    now = now or dt.datetime.now(dt.timezone.utc).astimezone()
    _require_pricing_engine(request.pricing_engine, pricing_engines)
    underlying = provider.get_underlying_snapshot(request.symbol)
    underlying_price = as_float(get_first(underlying, "last_price", "cur_price", "price", default=None))
    if underlying_price is None:
        raise OptionsReportError(f"No underlying price available for {request.symbol}.")

    expiries = provider.get_option_expirations(request.symbol)
    if not expiries:
        raise OptionsReportError(f"No option expirations returned for {request.symbol}.")
    selected_expiry = request.expiry or nearest_expiry(expiries, today=now.date())
    chain_rows = provider.get_option_chain(request.symbol, selected_expiry)
    if not chain_rows:
        raise OptionsReportError(f"No option chain rows returned for {request.symbol} {selected_expiry}.")
    codes = [str(row.get("code", "")).strip() for row in chain_rows if str(row.get("code", "")).strip()]
    snapshot_rows = provider.get_market_snapshots(codes) if codes else []
    if codes and not snapshot_rows:
        raise OptionsReportError(f"No option contract snapshots returned for {request.symbol} {selected_expiry}.")
    contracts = build_option_contracts(chain_rows, snapshot_rows, selected_expiry)
    if codes and not contracts:
        raise OptionsReportError(
            f"No option contract snapshots produced usable contracts for {request.symbol} {selected_expiry}."
        )
    contract = select_contract(contracts, request, underlying_price)
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
    model = price_option_with_engine(
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
    model_edge = model.theoretical_value - contract.market_price
    model_edge_pct = model_edge / contract.market_price
    scenarios = build_scenarios(contract, underlying_price, volatility, years, request)
    mc_distribution = monte_carlo_option_distribution(
        contract.option_type,
        underlying_price,
        contract.strike,
        years,
        volatility,
        request.risk_free_rate,
        request.dividend_yield,
        iterations=2000,
        seed=11,
    )
    earnings = get_earnings_context(provider, request.symbol)
    verdict, thesis, risks = research_verdict(contract, model_edge_pct, volatility, request.historical_volatility, earnings)
    black_scholes_curve = build_black_scholes_curve(contract, underlying_price, volatility, years, request)
    monte_carlo_paths = build_monte_carlo_sample_paths(underlying_price, volatility, years, request)
    days_to_expiry = max((dt.date.fromisoformat(contract.expiry[:10]) - now.date()).days, 0)
    event_summary = event_risk_summary(earnings)
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
    return OptionsResearchReport(
        symbol=request.symbol,
        generated_at=now,
        underlying_price=underlying_price,
        contract=contract,
        model=model,
        model_edge=model_edge,
        model_edge_pct=model_edge_pct,
        fair_value_gap_pct=model_edge_pct,
        valuation_view=valuation_view(model_edge_pct),
        implied_volatility_used=volatility,
        historical_volatility=request.historical_volatility,
        scenario_rows=scenarios,
        monte_carlo_distribution=monte_carlo_distribution_buckets(mc_distribution),
        smile_curve=build_smile_curve(chain_rows, snapshot_rows, selected_expiry),
        years_to_expiry=years,
        risk_free_rate=request.risk_free_rate,
        dividend_yield=request.dividend_yield,
        black_scholes_curve=black_scholes_curve,
        monte_carlo_paths=monte_carlo_paths,
        pricing_engine=request.pricing_engine,
        shadow_compare=request.shadow_compare,
        quantlib_vs_legacy_diff=shadow_summary,
        verdict=verdict,
        thesis=thesis,
        risks=risks,
        earnings=earnings,
        resale_thesis_summary=resale_thesis_summary(
            contract,
            valuation=valuation_view(model_edge_pct),
            model_edge_pct=model_edge_pct,
            event_summary=event_summary,
        ),
        exit_quality_summary=exit_quality_summary(
            contract,
            target_days_out=request.days_forward,
            days_to_expiry=days_to_expiry,
            delta_band=(0.20, 0.60),
        ),
        event_risk_summary=event_summary,
    )


def format_pct(value: float) -> str:
    return f"{value:.1%}"


def format_money(value: float) -> str:
    return f"{value:.2f}"


def _pricing_migration_section(report: OptionsResearchReport) -> dict[str, object] | None:
    summary = report.quantlib_vs_legacy_diff
    if not report.shadow_compare or not summary:
        return None
    if summary.get("status") != "ok":
        return {
            "title": "Pricing Engine Migration Check",
            "content": (
                f"Shadow compare is enabled, but the {summary.get('comparison_engine', 'comparison')} engine is unavailable. "
                "The active report still uses the selected pricing engine."
            ),
        }

    metric_labels = {
        "theoretical_value": "Theoretical Value",
        "delta": "Delta",
        "gamma": "Gamma",
        "theta": "Theta / Day",
        "vega": "Vega / Vol Point",
        "rho": "Rho / Rate Point",
        "implied_volatility": "Implied Volatility",
    }
    table = []
    active_values = summary["active_values"]
    comparison_values = summary["comparison_values"]
    diffs = summary["diffs"]
    tolerances = summary["tolerances"]
    for metric, label in metric_labels.items():
        table.append(
            {
                "metric": label,
                "active": f"{float(active_values[metric]):.4f}",
                "comparison": f"{float(comparison_values[metric]):.4f}",
                "abs_diff": f"{float(diffs[metric]):.4f}",
                "tolerance": f"{float(tolerances[metric]):.4f}",
            }
        )
    status = "inside" if summary.get("within_tolerance") else "outside"
    return {
        "title": "Pricing Engine Migration Check",
        "summary": (
            f"Active engine: {summary['active_engine']}. Comparison engine: {summary['comparison_engine']}. "
            f"Current parity is {status} the configured migration tolerances."
        ),
        "table": table,
    }


def options_report_sections(
    report: OptionsResearchReport,
    *,
    include_visual_explainer: bool = False,
) -> list[dict[str, object]]:
    scenario_rows = [
        {
            "price_shock": format_pct(row.price_shock_pct),
            "iv_shift": format_pct(row.iv_shift_pct),
            "underlying": format_money(row.underlying_price),
            "estimated_value": format_money(row.option_value),
            "profit_loss": format_money(row.profit_loss),
        }
        for row in report.scenario_rows
    ]
    base_iv_rows = [
        {"label": format_pct(row.price_shock_pct), "value": row.profit_loss}
        for row in report.scenario_rows
        if abs(row.iv_shift_pct) < 0.0001
    ]
    setup_copy = (
        f"The contract is not a directional headline trade by itself. The useful question is whether the premium is paying "
        f"fairly for movement, time, and event risk. At {format_pct(report.implied_volatility_used)} IV, the screen says "
        f"{report.verdict.lower()}: enough to track, but still governed by liquidity, spread discipline, and the next catalyst."
    )
    sections: list[dict[str, object]] = [
        {"title": "Desk View", "content": f"{report.thesis}\n\n{setup_copy}"},
        {
            "title": "Resale Lane Read",
            "items": [
                report.resale_thesis_summary,
                report.exit_quality_summary,
                report.event_risk_summary,
            ],
        },
        {
            "title": "Tear Sheet Read",
            "items": [
                "Strike is the contract exercise reference price, not a target price.",
                "Fair Value Gap % compares blended model value against the observed premium.",
                f"This contract reads as {report.valuation_view.lower()} on value: negative gap means rich, positive gap means cheap.",
                "The report is a review packet, not a trading instruction.",
            ],
        },
        {
            "title": "Contract Snapshot",
            "table": [
                {"metric": "Symbol", "value": report.symbol},
                {"metric": "Contract", "value": report.contract.code},
                {"metric": "Type", "value": report.contract.option_type},
                {"metric": "Strike", "value": format_money(report.contract.strike)},
                {"metric": "Expiry", "value": report.contract.expiry},
                {"metric": "Market Price", "value": format_money(report.contract.market_price)},
                {"metric": "Underlying", "value": format_money(report.underlying_price)},
                {"metric": "Open Interest", "value": f"{report.contract.open_interest:,}"},
                {"metric": "Volume", "value": f"{report.contract.volume:,}"},
            ],
        },
        {
            "title": "Model Interpretation",
            "table": [
                {"metric": "Fair Value", "value": format_money(report.model.theoretical_value)},
                {"metric": "Fair Value Gap", "value": f"{format_money(report.model_edge)} ({format_pct(report.fair_value_gap_pct)})"},
                {"metric": "Valuation View", "value": report.valuation_view},
                {"metric": "Pricing Engine", "value": report.pricing_engine},
                {"metric": "Shadow Compare", "value": "On" if report.shadow_compare else "Off"},
                {"metric": "IV / HV", "value": f"{format_pct(report.implied_volatility_used)} / {format_pct(report.historical_volatility)}"},
                {"metric": "Delta", "value": f"{report.model.delta:.3f}"},
                {"metric": "Gamma", "value": f"{report.model.gamma:.4f}"},
                {"metric": "Theta / Day", "value": f"{report.model.theta:.4f}"},
                {"metric": "Vega / Vol Point", "value": f"{report.model.vega:.4f}"},
                {"metric": "Rho / Rate Point", "value": f"{report.model.rho:.4f}"},
            ],
        },
        {
            "title": "Scenario Shape",
            "summary": "Estimated option P/L after the forward time step, holding IV flat. This is the quick visual check before reading the full matrix.",
            "chart": {"rows": base_iv_rows},
        },
        {"title": "Monte Carlo Distribution", "chart": {"rows": report.monte_carlo_distribution}},
        {"title": "Smile Curve", "chart": {"rows": [{"label": str(row["label"]), "value": float(row["value"])} for row in report.smile_curve]}},
        {"title": "Scenario Matrix", "table": scenario_rows},
        {
            "title": "Event Context",
            "content": (
                f"{report.earnings.phase}: {report.earnings.summary}\n\n"
                f"Risk label: {classify_event_risk(report.earnings)}.\n\n"
                "The desk read is intentionally conservative: if the catalyst is not mapped, the model should not pretend the premium is clean."
            ),
        },
        {"title": "Risk Register", "items": report.risks},
        {"title": "Verdict", "content": f"{report.verdict}\n\n{RISK_NOTE}"},
    ]
    migration_section = _pricing_migration_section(report)
    if migration_section is not None:
        sections.insert(4, migration_section)
    if include_visual_explainer:
        sections[4:4] = [
            {
                "title": "Black-Scholes Inputs",
                "summary": "This closed-form pricing check holds contract terms fixed and asks how theoretical value responds to spot, time, volatility, rates, and dividends.",
                "table": [
                    {"metric": "Spot", "value": format_money(report.underlying_price)},
                    {"metric": "Strike", "value": format_money(report.contract.strike)},
                    {"metric": "Years To Expiry", "value": f"{report.years_to_expiry:.4f}"},
                    {"metric": "Implied Volatility", "value": format_pct(report.implied_volatility_used)},
                    {"metric": "Risk-Free Rate", "value": format_pct(report.risk_free_rate)},
                    {"metric": "Dividend Yield", "value": format_pct(report.dividend_yield)},
                ],
            },
            {
                "title": "Black-Scholes Value Curve",
                "summary": "Hold IV and time fixed, then move spot across a small range to see how the model price bends around the selected strike.",
                "chart": {"type": "line", "rows": report.black_scholes_curve},
            },
            {
                "title": "Monte Carlo Sample Paths",
                "summary": "Representative simulated underlying paths using the same volatility and expiry horizon. They are scenario draws for intuition, not forecasts.",
                "chart": {"type": "line", "series": report.monte_carlo_paths},
            },
        ]
    return sections


def format_options_telegram_html(report: OptionsResearchReport, include_image: bool = True) -> str:
    generated = report.generated_at.strftime("%Y-%m-%d %H:%M %Z").strip()
    lines = [
        f"<b>{html.escape(report.symbol)} Options Desk Note</b>",
        f"<code>{html.escape(generated)}</code>",
        f"Contract: <code>{html.escape(report.contract.code)}</code>",
        f"View: <b>{html.escape(report.verdict)}</b>",
        f"Fair / Mkt: <code>{format_money(report.model.theoretical_value)} / {format_money(report.contract.market_price)}</code>",
        f"Gap: <code>{html.escape(format_pct(report.fair_value_gap_pct))}</code> ({html.escape(report.valuation_view)}) | IV/HV: <code>{html.escape(format_pct(report.implied_volatility_used))}/{html.escape(format_pct(report.historical_volatility))}</code>",
        "",
        html.escape(report.thesis[:360]),
        "",
        "Full image/report attached." if include_image else "Full report attached.",
        html.escape(RISK_NOTE),
    ]
    return "\n".join(lines)
