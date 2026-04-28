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
    OptionsResearchRequest,
    black_scholes,
    build_options_research_report,
    format_options_telegram_html,
    implied_volatility,
    options_report_sections,
)


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
    assert report.verdict in {"Research Candidate", "Watchlist", "Reject"}
    assert "earnings" in report.earnings.summary


def test_options_report_sections_include_required_report_blocks() -> None:
    report = build_options_research_report(
        FixtureOptionsResearchProvider(),
        OptionsResearchRequest(symbol="US.TEST", option_code="US.TEST260515C100000"),
        now=dt.datetime(2026, 4, 28, 9, 30, tzinfo=dt.timezone.utc),
    )

    sections = {str(section["title"]): section for section in options_report_sections(report)}

    assert "Desk View" in sections
    assert "Contract Snapshot" in sections
    assert "Scenario Matrix" in sections
    assert "table" in sections["Scenario Matrix"]
    assert sections["Scenario Matrix"]["table"][0]["price_shock"] == "-10.0%"  # type: ignore[index]
    assert "Verdict" in sections


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
