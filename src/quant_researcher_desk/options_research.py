"""Options pricing, scenario simulation, and research verdicts."""

from __future__ import annotations

import datetime as dt
import html
import math
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


TRADING_DAYS = 252
CALENDAR_DAYS = 365


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


@dataclass(frozen=True)
class OptionsResearchReport:
    symbol: str
    generated_at: dt.datetime
    underlying_price: float
    contract: OptionContract
    model: BlackScholesResult
    model_edge: float
    model_edge_pct: float
    implied_volatility_used: float
    historical_volatility: float
    scenario_rows: list[ScenarioRow]
    verdict: str
    thesis: str
    risks: list[str]
    earnings: EarningsContext


class FixtureOptionsResearchProvider:
    """Deterministic provider used for offline tests and cron dry-runs."""

    def get_underlying_snapshot(self, symbol: str) -> dict[str, Any]:
        return {"code": symbol, "last_price": 100.0}

    def get_option_expirations(self, symbol: str) -> list[str]:
        return ["2026-05-15", "2026-06-19"]

    def get_option_chain(self, symbol: str, expiry: str) -> list[dict[str, Any]]:
        return [
            {"code": f"{symbol}260515C100000", "option_type": "CALL", "strike_price": 100.0, "strike_time": expiry},
            {"code": f"{symbol}260515C105000", "option_type": "CALL", "strike_price": 105.0, "strike_time": expiry},
            {"code": f"{symbol}260515P95000", "option_type": "PUT", "strike_price": 95.0, "strike_time": expiry},
        ]

    def get_market_snapshots(self, codes: list[str]) -> list[dict[str, Any]]:
        rows = []
        for code in codes:
            if code.endswith("C100000"):
                rows.append({"code": code, "last_price": 4.2, "implied_volatility": 0.32, "delta": 0.54, "open_interest": 1500, "volume": 420})
            elif code.endswith("C105000"):
                rows.append({"code": code, "last_price": 2.1, "implied_volatility": 0.34, "delta": 0.34, "open_interest": 900, "volume": 240})
            else:
                rows.append({"code": code, "last_price": 1.8, "implied_volatility": 0.36, "delta": -0.28, "open_interest": 700, "volume": 180})
        return rows

    def get_earnings_context(self, symbol: str) -> EarningsContext:
        return EarningsContext(
            next_date="2026-05-07",
            phase="pre-earnings",
            summary="Fixture context: earnings are inside the option window, so IV and gap risk require explicit sizing discipline.",
        )


def normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def normal_pdf(value: float) -> float:
    return math.exp(-0.5 * value * value) / math.sqrt(2.0 * math.pi)


def years_to_expiry(expiry: str, now: dt.datetime) -> float:
    expiry_date = dt.date.fromisoformat(expiry[:10])
    days = max((expiry_date - now.date()).days, 0)
    return max(days / CALENDAR_DAYS, 1 / CALENDAR_DAYS)


def black_scholes(
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
    if market_price <= 0:
        raise OptionsReportError("Market price must be positive to solve implied volatility.")
    for _ in range(max_iterations):
        mid = (low + high) / 2
        value = black_scholes(option_type, spot, strike, years, mid, risk_free_rate, dividend_yield).theoretical_value
        if abs(value - market_price) <= tolerance:
            return mid
        if value > market_price:
            high = mid
        else:
            low = mid
    return (low + high) / 2


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
    return EarningsContext(next_date=None, phase="unknown", summary="No earnings context provider configured; treat event timing as an explicit uncertainty.")


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


def research_verdict(contract: OptionContract, model_edge_pct: float, volatility: float, historical_volatility: float) -> tuple[str, str, list[str]]:
    risks: list[str] = []
    if contract.volume < 50 or contract.open_interest < 100:
        risks.append("Liquidity is thin; volume or open interest is below the minimum research threshold.")
    if volatility > historical_volatility * 1.35:
        risks.append("Implied volatility is materially above historical volatility; premium may already price in the catalyst.")
    if abs(contract.delta or 0.0) < 0.20:
        risks.append("Delta is low, so the contract may require a large underlying move before thesis expression is meaningful.")

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
) -> OptionsResearchReport:
    now = now or dt.datetime.now(dt.timezone.utc).astimezone()
    underlying = provider.get_underlying_snapshot(request.symbol)
    underlying_price = as_float(get_first(underlying, "last_price", "cur_price", "price", default=None))
    if underlying_price is None:
        raise OptionsReportError(f"No underlying price available for {request.symbol}.")

    selected_expiry = request.expiry or nearest_expiry(provider.get_option_expirations(request.symbol), today=now.date())
    chain_rows = provider.get_option_chain(request.symbol, selected_expiry)
    codes = [str(row.get("code", "")).strip() for row in chain_rows if str(row.get("code", "")).strip()]
    snapshot_rows = provider.get_market_snapshots(codes) if codes else []
    contracts = build_option_contracts(chain_rows, snapshot_rows, selected_expiry)
    contract = select_contract(contracts, request, underlying_price)
    years = years_to_expiry(contract.expiry, now)
    volatility = contract.implied_volatility or implied_volatility(
        contract.option_type,
        contract.market_price,
        underlying_price,
        contract.strike,
        years,
        request.risk_free_rate,
        request.dividend_yield,
    )
    model = black_scholes(contract.option_type, underlying_price, contract.strike, years, volatility, request.risk_free_rate, request.dividend_yield)
    model_edge = model.theoretical_value - contract.market_price
    model_edge_pct = model_edge / contract.market_price
    scenarios = build_scenarios(contract, underlying_price, volatility, years, request)
    verdict, thesis, risks = research_verdict(contract, model_edge_pct, volatility, request.historical_volatility)
    return OptionsResearchReport(
        symbol=request.symbol,
        generated_at=now,
        underlying_price=underlying_price,
        contract=contract,
        model=model,
        model_edge=model_edge,
        model_edge_pct=model_edge_pct,
        implied_volatility_used=volatility,
        historical_volatility=request.historical_volatility,
        scenario_rows=scenarios,
        verdict=verdict,
        thesis=thesis,
        risks=risks,
        earnings=get_earnings_context(provider, request.symbol),
    )


def format_pct(value: float) -> str:
    return f"{value:.1%}"


def format_money(value: float) -> str:
    return f"{value:.2f}"


def options_report_sections(report: OptionsResearchReport) -> list[dict[str, object]]:
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
    return [
        {"title": "Desk View", "content": f"{report.thesis}\n\n{setup_copy}"},
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
                {"metric": "Model Edge", "value": f"{format_money(report.model_edge)} ({format_pct(report.model_edge_pct)})"},
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
        {"title": "Scenario Matrix", "table": scenario_rows},
        {
            "title": "Event Context",
            "content": (
                f"{report.earnings.phase}: {report.earnings.summary}\n\n"
                "The desk read is intentionally conservative: if the catalyst is not mapped, the model should not pretend the premium is clean."
            ),
        },
        {"title": "Risk Register", "items": report.risks},
        {"title": "Verdict", "content": f"{report.verdict}\n\n{RISK_NOTE}"},
    ]


def format_options_telegram_html(report: OptionsResearchReport, include_image: bool = True) -> str:
    generated = report.generated_at.strftime("%Y-%m-%d %H:%M %Z").strip()
    lines = [
        f"<b>{html.escape(report.symbol)} Options Desk Note</b>",
        f"<code>{html.escape(generated)}</code>",
        f"Contract: <code>{html.escape(report.contract.code)}</code>",
        f"View: <b>{html.escape(report.verdict)}</b>",
        f"Fair / Mkt: <code>{format_money(report.model.theoretical_value)} / {format_money(report.contract.market_price)}</code>",
        f"Edge: <code>{html.escape(format_pct(report.model_edge_pct))}</code> | IV/HV: <code>{html.escape(format_pct(report.implied_volatility_used))}/{html.escape(format_pct(report.historical_volatility))}</code>",
        "",
        html.escape(report.thesis[:360]),
        "",
        "Full image/report attached." if include_image else "Full report attached.",
        html.escape(RISK_NOTE),
    ]
    return "\n".join(lines)
