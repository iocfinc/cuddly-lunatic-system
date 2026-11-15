"""Defined-risk strategy routing for vetted option contracts."""

from __future__ import annotations

from dataclasses import dataclass

from quant_researcher_desk.options_research import OptionContract


@dataclass(frozen=True)
class StrategyLegRoute:
    action: str
    option_type: str
    strike: float
    premium: float
    code: str


@dataclass(frozen=True)
class RoutedStrategy:
    name: str
    structure: str
    legs: tuple[StrategyLegRoute, ...]
    net_debit: float
    net_credit: float
    max_loss: float
    max_profit: float | None
    breakeven: float
    breakeven_move_pct: float
    model_edge_pct: float
    liquidity_score: float
    score: float
    risk_notes: tuple[str, ...]
    rejection_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class StrategyRouteRequest:
    contracts: tuple[OptionContract, ...]
    selected_contract: OptionContract
    underlying_price: float
    direction: str
    implied_volatility: float
    historical_volatility: float
    model_edge_pct: float
    max_breakeven_move_pct: float = 0.15
    max_loss_per_contract: float | None = None
    include_income: bool = True
    allow_credit_spreads: bool = True


@dataclass(frozen=True)
class StrategyRoute:
    verdict: str
    selected: RoutedStrategy | None
    candidates: tuple[RoutedStrategy, ...]
    rejected: tuple[RoutedStrategy, ...]
    rejection_reasons: tuple[str, ...]


def _leg(action: str, contract: OptionContract) -> StrategyLegRoute:
    return StrategyLegRoute(
        action=action,
        option_type=contract.option_type,
        strike=contract.strike,
        premium=contract.market_price,
        code=contract.code,
    )


def _liquidity_score(*contracts: OptionContract) -> float:
    if not contracts:
        return 0.0
    scores = []
    for contract in contracts:
        volume_score = min(contract.volume / 500, 1.0)
        open_interest_score = min(contract.open_interest / 1000, 1.0)
        scores.append((volume_score + open_interest_score) / 2)
    return round(min(scores), 4)


def _breakeven_move(breakeven: float, underlying_price: float) -> float:
    if underlying_price <= 0:
        return 1.0
    return abs(breakeven / underlying_price - 1.0)


def _with_score(strategy: RoutedStrategy, request: StrategyRouteRequest, *, defined_risk_bonus: float = 0.0) -> RoutedStrategy:
    iv_penalty = max(request.implied_volatility - request.historical_volatility * 1.35, 0.0)
    breakeven_penalty = strategy.breakeven_move_pct / max(request.max_breakeven_move_pct, 0.01)
    profit_reward = (
        min((strategy.max_profit or 0.0) / max(strategy.max_loss, 0.01), 2.0) * 0.12
        if strategy.max_profit is not None
        else 0.0
    )
    score = (
        strategy.liquidity_score
        + strategy.model_edge_pct
        + defined_risk_bonus
        + profit_reward
        - breakeven_penalty * 0.35
        - iv_penalty * 0.40
    )
    return RoutedStrategy(**{**strategy.__dict__, "score": round(score, 4)})


def _long_option_candidate(request: StrategyRouteRequest) -> RoutedStrategy:
    contract = request.selected_contract
    breakeven = contract.strike + contract.market_price if contract.option_type == "CALL" else contract.strike - contract.market_price
    structure = "long_call" if contract.option_type == "CALL" else "long_put"
    strategy = RoutedStrategy(
        name="Long Call" if contract.option_type == "CALL" else "Long Put",
        structure=structure,
        legs=(_leg("buy", contract),),
        net_debit=round(contract.market_price, 4),
        net_credit=0.0,
        max_loss=round(contract.market_price, 4),
        max_profit=None,
        breakeven=round(breakeven, 4),
        breakeven_move_pct=round(_breakeven_move(breakeven, request.underlying_price), 6),
        model_edge_pct=request.model_edge_pct,
        liquidity_score=_liquidity_score(contract),
        score=0.0,
        risk_notes=("Full premium is at risk and the breakeven must be reached before expiry.",),
    )
    return _with_score(strategy, request)


def _spread_partner(contracts: tuple[OptionContract, ...], selected: OptionContract, *, debit: bool) -> OptionContract | None:
    same_side = [
        contract
        for contract in contracts
        if contract.option_type == selected.option_type
        and contract.expiry == selected.expiry
        and contract.code != selected.code
    ]
    if selected.option_type == "CALL":
        candidates = [contract for contract in same_side if contract.strike > selected.strike]
        return sorted(candidates, key=lambda contract: contract.strike)[0] if candidates else None
    candidates = [contract for contract in same_side if contract.strike < selected.strike]
    return sorted(candidates, key=lambda contract: contract.strike, reverse=True)[0] if candidates else None


def _debit_spread_candidate(request: StrategyRouteRequest) -> RoutedStrategy | None:
    long_contract = request.selected_contract
    short_contract = _spread_partner(request.contracts, long_contract, debit=True)
    if short_contract is None:
        return None
    net_debit = long_contract.market_price - short_contract.market_price
    width = abs(short_contract.strike - long_contract.strike)
    max_profit = width - net_debit
    if net_debit <= 0 or max_profit <= 0:
        return None
    breakeven = long_contract.strike + net_debit if long_contract.option_type == "CALL" else long_contract.strike - net_debit
    structure = "call_debit_spread" if long_contract.option_type == "CALL" else "put_debit_spread"
    strategy = RoutedStrategy(
        name="Call Debit Spread" if long_contract.option_type == "CALL" else "Put Debit Spread",
        structure=structure,
        legs=(_leg("buy", long_contract), _leg("sell", short_contract)),
        net_debit=round(net_debit, 4),
        net_credit=0.0,
        max_loss=round(net_debit, 4),
        max_profit=round(max_profit, 4),
        breakeven=round(breakeven, 4),
        breakeven_move_pct=round(_breakeven_move(breakeven, request.underlying_price), 6),
        model_edge_pct=request.model_edge_pct + 0.03,
        liquidity_score=_liquidity_score(long_contract, short_contract),
        score=0.0,
        risk_notes=("defined risk; short leg caps upside but lowers the premium and breakeven.",),
    )
    return _with_score(strategy, request, defined_risk_bonus=0.16)


def _credit_spread_candidate(request: StrategyRouteRequest) -> RoutedStrategy | None:
    short_contract = request.selected_contract
    long_contract = _spread_partner(request.contracts, short_contract, debit=False)
    if long_contract is None:
        return None
    net_credit = short_contract.market_price - long_contract.market_price
    width = abs(short_contract.strike - long_contract.strike)
    max_loss = width - net_credit
    if net_credit <= 0 or max_loss <= 0:
        return None
    breakeven = short_contract.strike - net_credit if short_contract.option_type == "PUT" else short_contract.strike + net_credit
    structure = "put_credit_spread" if short_contract.option_type == "PUT" else "call_credit_spread"
    iv_bonus = max(request.implied_volatility - request.historical_volatility, 0.0) * 0.25
    strategy = RoutedStrategy(
        name="Put Credit Spread" if short_contract.option_type == "PUT" else "Call Credit Spread",
        structure=structure,
        legs=(_leg("sell", short_contract), _leg("buy", long_contract)),
        net_debit=0.0,
        net_credit=round(net_credit, 4),
        max_loss=round(max_loss, 4),
        max_profit=round(net_credit, 4),
        breakeven=round(breakeven, 4),
        breakeven_move_pct=round(_breakeven_move(breakeven, request.underlying_price), 6),
        model_edge_pct=max(-request.model_edge_pct, 0.0) + iv_bonus,
        liquidity_score=_liquidity_score(short_contract, long_contract),
        score=0.0,
        risk_notes=("defined risk credit spread; benefits from time decay but must respect short-strike risk.",),
    )
    return _with_score(strategy, request, defined_risk_bonus=0.18)


def _income_candidate(request: StrategyRouteRequest) -> RoutedStrategy:
    contract = request.selected_contract
    if contract.option_type == "CALL":
        breakeven = request.underlying_price - contract.market_price
        structure = "covered_call_research"
        name = "Covered Call Research"
        notes = "Requires stock ownership and caps upside; included as research context only."
        max_profit = max(contract.strike - request.underlying_price, 0.0) + contract.market_price
        max_loss = max(request.underlying_price - contract.market_price, 0.0)
        legs = (StrategyLegRoute("hold", "STOCK", request.underlying_price, request.underlying_price, "UNDERLYING"), _leg("sell", contract))
    else:
        breakeven = contract.strike - contract.market_price
        structure = "cash_secured_put_research"
        name = "Cash-Secured Put Research"
        notes = "Assignment risk is explicit; included only if owning shares at the effective basis is acceptable."
        max_profit = contract.market_price
        max_loss = max(contract.strike - contract.market_price, 0.0)
        legs = (_leg("sell", contract), StrategyLegRoute("reserve", "CASH", contract.strike, max_loss, "CASH_COLLATERAL"))
    strategy = RoutedStrategy(
        name=name,
        structure=structure,
        legs=legs,
        net_debit=0.0,
        net_credit=round(contract.market_price, 4),
        max_loss=round(max_loss, 4),
        max_profit=round(max_profit, 4),
        breakeven=round(breakeven, 4),
        breakeven_move_pct=round(_breakeven_move(breakeven, request.underlying_price), 6),
        model_edge_pct=max(-request.model_edge_pct, 0.0),
        liquidity_score=_liquidity_score(contract),
        score=0.0,
        risk_notes=(notes,),
    )
    return _with_score(strategy, request, defined_risk_bonus=-0.05)


def _candidate_rejection(strategy: RoutedStrategy, request: StrategyRouteRequest) -> str | None:
    if strategy.max_loss <= 0:
        return f"{strategy.structure} rejected: max loss is not measurable."
    if request.max_loss_per_contract is not None and strategy.max_loss > request.max_loss_per_contract:
        return (
            f"{strategy.structure} rejected: max loss {strategy.max_loss:.2f} "
            f"exceeds {request.max_loss_per_contract:.2f}."
        )
    if strategy.breakeven_move_pct > request.max_breakeven_move_pct:
        return (
            f"{strategy.structure} rejected: breakeven move {strategy.breakeven_move_pct:.1%} "
            f"exceeds {request.max_breakeven_move_pct:.1%}."
        )
    if strategy.liquidity_score < 0.25:
        return f"{strategy.structure} rejected: liquidity score {strategy.liquidity_score:.2f} is too weak."
    return None


def route_option_strategies(request: StrategyRouteRequest) -> StrategyRoute:
    raw_candidates: list[RoutedStrategy] = [_long_option_candidate(request)]
    if request.include_income:
        raw_candidates.append(_income_candidate(request))
    debit = _debit_spread_candidate(request)
    if debit is not None:
        raw_candidates.append(debit)
    credit = _credit_spread_candidate(request) if request.allow_credit_spreads else None
    if credit is not None:
        raw_candidates.append(credit)

    accepted: list[RoutedStrategy] = []
    rejected: list[RoutedStrategy] = []
    rejection_reasons: list[str] = []
    for candidate in raw_candidates:
        reason = _candidate_rejection(candidate, request)
        if reason:
            rejected.append(RoutedStrategy(**{**candidate.__dict__, "rejection_reasons": (reason,)}))
            rejection_reasons.append(reason)
        else:
            accepted.append(candidate)

    accepted.sort(key=lambda candidate: candidate.score, reverse=True)
    selected = accepted[0] if accepted else None
    return StrategyRoute(
        verdict="selected" if selected is not None else "no_trade",
        selected=selected,
        candidates=tuple(accepted),
        rejected=tuple(rejected),
        rejection_reasons=tuple(rejection_reasons),
    )
