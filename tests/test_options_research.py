from __future__ import annotations

import datetime as dt
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quant_researcher_desk.options_research import (
    BlackScholesResult,
    FixtureOptionsResearchProvider,
    HistoricalVolatilityContext,
    OptionsResearchRequest,
    analyst_desk_note,
    black_scholes,
    build_options_research_report,
    format_options_telegram_html,
    implied_volatility,
    options_report_sections,
)


class FakeQuantLibEngine:
    name = "quantlib"

    def is_available(self) -> bool:
        return True

    def price(
        self,
        option_type: str,
        spot: float,
        strike: float,
        years: float,
        volatility: float,
        risk_free_rate: float = 0.04,
        dividend_yield: float = 0.0,
    ) -> BlackScholesResult:
        base = black_scholes(
            option_type,
            spot=spot,
            strike=strike,
            years=years,
            volatility=volatility,
            risk_free_rate=risk_free_rate,
            dividend_yield=dividend_yield,
        )
        return BlackScholesResult(
            theoretical_value=base.theoretical_value + 0.01,
            delta=base.delta + 0.0005,
            gamma=base.gamma + 0.0001,
            theta=base.theta - 0.0005,
            vega=base.vega + 0.0005,
            rho=base.rho + 0.0005,
        )

    def solve_implied_volatility(
        self,
        option_type: str,
        market_price: float,
        spot: float,
        strike: float,
        years: float,
        risk_free_rate: float = 0.04,
        dividend_yield: float = 0.0,
    ) -> float:
        return implied_volatility(
            option_type,
            market_price=market_price,
            spot=spot,
            strike=strike,
            years=years,
            risk_free_rate=risk_free_rate,
            dividend_yield=dividend_yield,
        ) + 0.0005


def test_black_scholes_call_matches_reference_value() -> None:
    result = black_scholes("CALL", spot=100, strike=100, years=1, volatility=0.20, risk_free_rate=0.05)

    assert isinstance(result, BlackScholesResult)
    assert result.theoretical_value == pytest.approx(10.4506, abs=0.0001)
    assert result.delta == pytest.approx(0.6368, abs=0.0001)
    assert result.gamma == pytest.approx(0.0188, abs=0.0001)
    assert result.vega == pytest.approx(0.3752, abs=0.0001)


def test_implied_volatility_solves_back_to_reference_vol() -> None:
    market_price = black_scholes("PUT", spot=100, strike=95, years=0.5, volatility=0.32, risk_free_rate=0.04).theoretical_value

    solved = implied_volatility("PUT", market_price=market_price, spot=100, strike=95, years=0.5, risk_free_rate=0.04)

    assert solved == pytest.approx(0.32, abs=0.0001)


def test_build_options_research_report_uses_fixture_provider_and_scores_verdict() -> None:
    report = build_options_research_report(
        FixtureOptionsResearchProvider(),
        OptionsResearchRequest(symbol="US.TEST", option_type="CALL", strike=100, historical_volatility=0.30),
        now=dt.datetime(2026, 4, 28, 9, 30, tzinfo=dt.timezone.utc),
    )

    assert report.symbol == "US.TEST"
    assert report.contract.code == "US.TEST260515C100000"
    assert report.contract.volume == 420
    assert report.implied_volatility_used == 0.32
    assert len(report.scenario_rows) == 15
    assert report.valuation_view in {"Cheap", "Near Fair", "Rich"}
    assert report.monte_carlo_distribution
    assert report.smile_curve
    assert report.verdict in {"Research Candidate", "Watchlist", "Reject"}
    assert "earnings" in report.earnings.summary
    assert "resale" in report.resale_thesis_summary.lower()
    assert "exit quality" in report.exit_quality_summary.lower()
    assert "holding window" in report.event_risk_summary.lower()


def test_options_research_uses_provider_historical_volatility_context() -> None:
    class HistoricalVolatilityProvider(FixtureOptionsResearchProvider):
        def get_historical_volatility(self, symbol: str) -> HistoricalVolatilityContext:
            return HistoricalVolatilityContext(
                value=0.27,
                source="fixture-hv",
                status="fixture-backed",
                summary=f"{symbol} fixture HV from daily bars.",
                as_of="2026-04-27",
            )

    report = build_options_research_report(
        HistoricalVolatilityProvider(),
        OptionsResearchRequest(symbol="US.TEST", option_code="US.TEST260515C100000", historical_volatility=0.45),
        now=dt.datetime(2026, 4, 28, 9, 30, tzinfo=dt.timezone.utc),
    )

    sections = {str(section["title"]): section for section in options_report_sections(report)}

    assert report.historical_volatility == pytest.approx(0.27)
    assert report.historical_volatility_source == "fixture-hv"
    assert report.historical_volatility_status == "fixture-backed"
    assert "daily bars" in report.historical_volatility_summary
    assert "Context Freshness" in sections
    assert sections["Context Freshness"]["table"][1]["value"] == "fixture-hv"  # type: ignore[index]


def test_options_research_marks_missing_historical_volatility_context() -> None:
    class MissingHistoricalVolatilityProvider(FixtureOptionsResearchProvider):
        def get_historical_volatility(self, symbol: str) -> HistoricalVolatilityContext:
            raise RuntimeError(f"{symbol} daily bars unavailable")

    report = build_options_research_report(
        MissingHistoricalVolatilityProvider(),
        OptionsResearchRequest(symbol="US.TEST", option_code="US.TEST260515C100000", historical_volatility=0.41),
        now=dt.datetime(2026, 4, 28, 9, 30, tzinfo=dt.timezone.utc),
    )

    message = format_options_telegram_html(report)

    assert report.historical_volatility == pytest.approx(0.41)
    assert report.historical_volatility_status == "missing"
    assert "daily bars unavailable" in report.historical_volatility_summary
    assert "missing" in message


def test_options_report_sections_include_required_report_blocks() -> None:
    report = build_options_research_report(
        FixtureOptionsResearchProvider(),
        OptionsResearchRequest(symbol="US.TEST", option_code="US.TEST260515C100000"),
        now=dt.datetime(2026, 4, 28, 9, 30, tzinfo=dt.timezone.utc),
    )

    sections = {str(section["title"]): section for section in options_report_sections(report)}

    assert "Desk View" in sections
    assert "Resale Lane Read" in sections
    assert "Contract Snapshot" in sections
    assert "Scenario Matrix" in sections
    assert "table" in sections["Scenario Matrix"]
    assert sections["Scenario Matrix"]["table"][0]["price_shock"] == "-10.0%"  # type: ignore[index]
    assert "Tear Sheet Read" in sections
    assert "Verdict" in sections


def test_options_research_suppresses_strategy_comparison_without_gate() -> None:
    report = build_options_research_report(
        FixtureOptionsResearchProvider(),
        OptionsResearchRequest(symbol="US.TEST", option_code="US.TEST260515C100000"),
        now=dt.datetime(2026, 4, 28, 9, 30, tzinfo=dt.timezone.utc),
    )

    sections = {str(section["title"]): section for section in options_report_sections(report)}

    assert report.strategy_candidates == ()
    assert "Post-Gate Strategy Comparison" not in sections


def test_options_research_builds_post_gate_strategy_candidates() -> None:
    report = build_options_research_report(
        FixtureOptionsResearchProvider(),
        OptionsResearchRequest(
            symbol="US.TEST",
            option_code="US.TEST260515C100000",
            strategy_gate_passed=True,
            strategy_gate_reason="stock trend and liquidity gate passed",
        ),
        now=dt.datetime(2026, 4, 28, 9, 30, tzinfo=dt.timezone.utc),
    )

    sections = {str(section["title"]): section for section in options_report_sections(report)}
    strategy_names = {candidate.name for candidate in report.strategy_candidates}

    assert report.strategy_gate_passed is True
    assert "Long Call" in strategy_names
    assert "Call Debit Spread" in strategy_names
    assert "Covered Call" in strategy_names
    assert "Cash-Secured Put" in strategy_names
    assert all(candidate.net_debit >= 0 for candidate in report.strategy_candidates)
    assert all(candidate.directional_assumption for candidate in report.strategy_candidates)
    assert {candidate.context_freshness for candidate in report.strategy_candidates} == {"fixture-backed"}
    assert "Post-Gate Strategy Comparison" in sections
    assert "not execution instructions" in str(sections["Post-Gate Strategy Comparison"]["summary"])


def test_options_research_can_represent_long_put_strategy_candidates() -> None:
    report = build_options_research_report(
        FixtureOptionsResearchProvider(),
        OptionsResearchRequest(
            symbol="US.TEST",
            option_code="US.TEST260515P095000",
            strategy_gate_passed=True,
            strategy_gate_reason="bearish fixture gate passed",
        ),
        now=dt.datetime(2026, 4, 28, 9, 30, tzinfo=dt.timezone.utc),
    )

    strategy_names = {candidate.name for candidate in report.strategy_candidates}
    long_put = next(candidate for candidate in report.strategy_candidates if candidate.name == "Long Put")

    assert "Long Put" in strategy_names
    assert "Cash-Secured Put" in strategy_names
    assert long_put.directional_assumption == "bearish"


def test_analyst_desk_note_follows_voice_rubric_and_cites_metrics() -> None:
    report = build_options_research_report(
        FixtureOptionsResearchProvider(),
        OptionsResearchRequest(symbol="US.TEST", option_code="US.TEST260515C100000"),
        now=dt.datetime(2026, 4, 28, 9, 30, tzinfo=dt.timezone.utc),
    )

    note = analyst_desk_note(report)

    for label in ("Statement:", "Evidence:", "Interpretation:", "Risk:", "Verdict:"):
        assert label in note
    assert report.contract.code in note
    assert "IV/HV" in note
    assert "volume" in note
    assert "open interest" in note
    assert "Research output only, not a trading instruction." in note


def test_analyst_desk_note_avoids_hype_and_trade_directives() -> None:
    report = build_options_research_report(
        FixtureOptionsResearchProvider(),
        OptionsResearchRequest(symbol="US.TEST", option_code="US.TEST260515C100000"),
        now=dt.datetime(2026, 4, 28, 9, 30, tzinfo=dt.timezone.utc),
    )

    note = analyst_desk_note(report).lower()

    banned_phrases = ("buy now", "sure thing", "guaranteed", "moonshot", "must buy", "trading signal")
    assert not any(phrase in note for phrase in banned_phrases)


def test_options_research_defaults_event_risk_to_unknown_when_provider_has_no_event_method() -> None:
    class NoEventProvider:
        def __init__(self) -> None:
            self.base = FixtureOptionsResearchProvider()

        def get_underlying_snapshot(self, symbol: str):  # type: ignore[no-untyped-def]
            return self.base.get_underlying_snapshot(symbol)

        def get_option_expirations(self, symbol: str):  # type: ignore[no-untyped-def]
            return self.base.get_option_expirations(symbol)

        def get_option_chain(self, symbol: str, expiry: str):  # type: ignore[no-untyped-def]
            return self.base.get_option_chain(symbol, expiry)

        def get_market_snapshots(self, codes: list[str]):  # type: ignore[no-untyped-def]
            return self.base.get_market_snapshots(codes)

    report = build_options_research_report(
        NoEventProvider(),
        OptionsResearchRequest(symbol="US.TEST", option_code="US.TEST260515C100000"),
        now=dt.datetime(2026, 4, 28, 9, 30, tzinfo=dt.timezone.utc),
    )

    assert report.earnings.risk_level == "unknown"
    assert "unknown" in report.event_risk_summary.lower()
    assert any("Catalyst timing is unknown" in risk for risk in report.risks)


def test_options_report_sections_can_include_visual_explainer_blocks() -> None:
    report = build_options_research_report(
        FixtureOptionsResearchProvider(),
        OptionsResearchRequest(symbol="US.TEST", option_code="US.TEST260515C100000"),
        now=dt.datetime(2026, 4, 28, 9, 30, tzinfo=dt.timezone.utc),
    )

    sections = {str(section["title"]): section for section in options_report_sections(report, include_visual_explainer=True)}

    assert "Black-Scholes Value Curve" in sections
    assert sections["Black-Scholes Value Curve"]["chart"]["type"] == "line"  # type: ignore[index]
    assert "Monte Carlo Sample Paths" in sections
    assert sections["Monte Carlo Sample Paths"]["chart"]["type"] == "line"  # type: ignore[index]


def test_build_options_research_report_can_shadow_compare_legacy_and_quantlib_outputs() -> None:
    report = build_options_research_report(
        FixtureOptionsResearchProvider(),
        OptionsResearchRequest(
            symbol="US.TEST",
            option_code="US.TEST260515C100000",
            pricing_engine="legacy",
            shadow_compare=True,
        ),
        now=dt.datetime(2026, 4, 28, 9, 30, tzinfo=dt.timezone.utc),
        pricing_engines={"quantlib": FakeQuantLibEngine()},
    )

    assert report.pricing_engine == "legacy"
    assert report.shadow_compare is True
    assert report.quantlib_vs_legacy_diff is not None
    assert report.quantlib_vs_legacy_diff["comparison_engine"] == "quantlib"
    assert report.quantlib_vs_legacy_diff["status"] == "ok"
    assert report.quantlib_vs_legacy_diff["within_tolerance"] is True

    sections = {str(section["title"]): section for section in options_report_sections(report)}
    assert "Pricing Engine Migration Check" in sections
    assert sections["Pricing Engine Migration Check"]["table"][0]["metric"] == "Theoretical Value"  # type: ignore[index]


def test_options_telegram_html_escapes_and_summarizes_report() -> None:
    report = build_options_research_report(
        FixtureOptionsResearchProvider(),
        OptionsResearchRequest(symbol="US.TEST"),
        now=dt.datetime(2026, 4, 28, 9, 30, tzinfo=dt.timezone.utc),
    )

    message = format_options_telegram_html(report)

    assert "<b>US.TEST Options Desk Note</b>" in message
    assert "Contract: <code>US.TEST260515C100000</code>" in message
    assert "Research output only, not a trading instruction." in message
