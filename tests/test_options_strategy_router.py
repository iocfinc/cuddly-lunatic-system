from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quant_researcher_desk.options_research import OptionContract  # noqa: E402
from quant_researcher_desk.options_strategy_router import StrategyRouteRequest, route_option_strategies  # noqa: E402


def _contract(
    code: str,
    option_type: str,
    strike: float,
    premium: float,
    delta: float,
    iv: float = 0.35,
    volume: int = 900,
    open_interest: int = 1500,
) -> OptionContract:
    return OptionContract(
        code=code,
        option_type=option_type,
        strike=strike,
        expiry="2026-07-17",
        market_price=premium,
        implied_volatility=iv,
        delta=delta,
        open_interest=open_interest,
        volume=volume,
    )


def test_router_prefers_call_debit_spread_over_expensive_long_call() -> None:
    long_call = _contract("US.TEST260717C100000", "CALL", 100.0, 8.0, 0.52, iv=0.45)
    short_call = _contract("US.TEST260717C110000", "CALL", 110.0, 4.5, 0.31, iv=0.47)

    route = route_option_strategies(
        StrategyRouteRequest(
            contracts=(long_call, short_call),
            selected_contract=long_call,
            underlying_price=100.0,
            direction="bullish",
            implied_volatility=0.45,
            historical_volatility=0.28,
            model_edge_pct=0.03,
        )
    )

    assert route.verdict == "selected"
    assert route.selected is not None
    assert route.selected.structure == "call_debit_spread"
    assert route.selected.net_debit == 3.5
    assert route.selected.max_loss == 3.5
    assert route.selected.max_profit == 6.5
    assert route.selected.breakeven == 103.5
    assert route.selected.breakeven_move_pct < 0.05


def test_router_rejects_unrealistic_single_leg_breakeven() -> None:
    expensive_call = _contract("US.TEST260717C100000", "CALL", 100.0, 24.0, 0.52, iv=0.85)

    route = route_option_strategies(
        StrategyRouteRequest(
            contracts=(expensive_call,),
            selected_contract=expensive_call,
            underlying_price=100.0,
            direction="bullish",
            implied_volatility=0.85,
            historical_volatility=0.25,
            model_edge_pct=-0.20,
        )
    )

    assert route.verdict == "no_trade"
    assert route.selected is None
    assert any("breakeven" in reason for reason in route.rejection_reasons)


def test_router_can_select_credit_spread_when_iv_is_expensive() -> None:
    short_put = _contract("US.TEST260717P095000", "PUT", 95.0, 4.0, -0.34, iv=0.62)
    long_put = _contract("US.TEST260717P090000", "PUT", 90.0, 1.6, -0.22, iv=0.64)

    route = route_option_strategies(
        StrategyRouteRequest(
            contracts=(short_put, long_put),
            selected_contract=short_put,
            underlying_price=100.0,
            direction="bullish",
            implied_volatility=0.62,
            historical_volatility=0.24,
            model_edge_pct=-0.08,
        )
    )

    assert route.verdict == "selected"
    assert route.selected is not None
    assert route.selected.structure == "put_credit_spread"
    assert route.selected.net_credit == 2.4
    assert route.selected.max_loss == 2.6
    assert route.selected.max_profit == 2.4
    assert route.selected.breakeven == 92.6
    assert "defined risk" in " ".join(route.selected.risk_notes)
