from __future__ import annotations

import datetime as dt
import pathlib
import sys
from dataclasses import replace

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quant_researcher_desk.moomoo_options_report import OptionsReportError  # noqa: E402
from quant_researcher_desk.options_research import FixtureOptionsResearchProvider  # noqa: E402
from quant_researcher_desk.weekly_agent_review import WeeklyAgentReviewConfig, WeeklyAgentReviewResult  # noqa: E402
from quant_researcher_desk.weekly_options_packet import (  # noqa: E402
    _native_packet_sections,
    build_weekly_options_packet,
    render_weekly_options_packet_html,
)
from quant_researcher_desk.weekly_options_screener import FixtureWeeklyScreenProvider, WeeklyScreenRequest, build_weekly_options_screen  # noqa: E402


def test_build_weekly_options_packet_appends_tearsheets_for_each_shortlisted_contract() -> None:
    now = dt.datetime(2026, 5, 26, 9, 30, tzinfo=dt.timezone.utc)
    weekly = build_weekly_options_screen(
        FixtureWeeklyScreenProvider(anchor_date=now.date()),
        WeeklyScreenRequest(market="US", top_n=5, historical_volatility=0.22),
        now=now,
    )

    packet = build_weekly_options_packet(
        weekly,
        FixtureOptionsResearchProvider(anchor_date=now.date()),
        now=now,
    )

    assert packet.title == "US Weekly Options Packet"
    assert len(packet.tearsheets) == len(weekly.ranked_options)
    assert packet.tearsheets[0].contract.code == weekly.ranked_options[0].option_code


def test_build_weekly_options_packet_preserves_pricing_engine_metadata() -> None:
    now = dt.datetime(2026, 5, 26, 9, 30, tzinfo=dt.timezone.utc)
    weekly = build_weekly_options_screen(
        FixtureWeeklyScreenProvider(anchor_date=now.date()),
        WeeklyScreenRequest(
            market="US",
            top_n=3,
            historical_volatility=0.22,
            pricing_engine="legacy",
            shadow_compare=True,
        ),
        now=now,
    )

    packet = build_weekly_options_packet(
        weekly,
        FixtureOptionsResearchProvider(anchor_date=now.date()),
        now=now,
    )

    assert packet.tearsheets[0].report.pricing_engine == "legacy"
    assert packet.tearsheets[0].report.shadow_compare is True


def test_render_weekly_options_packet_html_includes_overview_and_tearsheets() -> None:
    now = dt.datetime(2026, 5, 26, 9, 30, tzinfo=dt.timezone.utc)
    weekly = build_weekly_options_screen(
        FixtureWeeklyScreenProvider(anchor_date=now.date()),
        WeeklyScreenRequest(market="US", top_n=3, historical_volatility=0.22),
        now=now,
    )
    packet = build_weekly_options_packet(
        weekly,
        FixtureOptionsResearchProvider(anchor_date=now.date()),
        now=now,
    )

    html = render_weekly_options_packet_html(packet)

    assert "US Weekly Options Packet" in html
    assert "Executive Overview" in html
    assert "How To Read This Packet" in html
    assert "Cleaner Resale Candidates" in html
    assert "Flagged Candidates" in html
    assert "Top 10 Weekly Shortlist" in html
    assert "Trend Regime" in html
    assert "Stock Direction" in html
    assert 'data-tab-target="overview"' in html
    assert 'data-tab-target="top-10"' in html
    assert html.count('data-tab-target="rank-') == len(packet.tearsheets)
    assert "Stock Context" in html
    assert "Catalyst View" in html
    assert "Monte Carlo Distribution" in html
    assert "Smile Curve" in html
    assert "Black-Scholes Value Curve" in html
    assert "Monte Carlo Sample Paths" in html
    assert "Event Risk" in html
    assert 'data-tab-target="agent-review"' not in html


def test_build_weekly_options_packet_keeps_warning_state_when_agent_review_fails(monkeypatch) -> None:
    now = dt.datetime(2026, 5, 26, 9, 30, tzinfo=dt.timezone.utc)
    weekly = build_weekly_options_screen(
        FixtureWeeklyScreenProvider(anchor_date=now.date()),
        WeeklyScreenRequest(market="US", top_n=3, historical_volatility=0.22),
        now=now,
    )

    def fake_review(packet, config):  # type: ignore[no-untyped-def]
        return None, ["primary failed", "fallback failed"]

    monkeypatch.setattr("quant_researcher_desk.weekly_options_packet.maybe_request_weekly_agent_review", fake_review)

    packet = build_weekly_options_packet(
        weekly,
        FixtureOptionsResearchProvider(anchor_date=now.date()),
        now=now,
        agent_review_config=WeeklyAgentReviewConfig(enabled=True, api_key="test-key"),
    )

    assert packet.agent_review is None
    assert packet.warnings == ("primary failed", "fallback failed")
    assert "Agent Review warning" in packet.executive_summary


def test_build_weekly_options_packet_retries_tearsheet_build_on_provider_rate_limit(monkeypatch) -> None:
    now = dt.datetime(2026, 5, 26, 9, 30, tzinfo=dt.timezone.utc)
    weekly = build_weekly_options_screen(
        FixtureWeeklyScreenProvider(anchor_date=now.date()),
        WeeklyScreenRequest(market="US", top_n=1, historical_volatility=0.22),
        now=now,
    )
    calls = 0

    def fake_builder(provider, request, now=None):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OptionsReportError(
                "OpenD failed to get option expirations: Get Option Chain Expiry Dates request failed due to high frequency. Maximum 60 times per 30 seconds."
            )
        from quant_researcher_desk.options_research import build_options_research_report as actual_builder

        return actual_builder(provider, request, now=now)

    monkeypatch.setattr("quant_researcher_desk.weekly_options_packet.build_options_research_report", fake_builder)
    monkeypatch.setattr("quant_researcher_desk.weekly_options_packet.time.sleep", lambda _: None)

    packet = build_weekly_options_packet(
        weekly,
        FixtureOptionsResearchProvider(anchor_date=now.date()),
        now=now,
        agent_review_config=WeeklyAgentReviewConfig(enabled=False),
    )

    assert calls == 2
    assert len(packet.tearsheets) == 1


def test_render_weekly_options_packet_html_only_shows_agent_review_tab_when_review_exists() -> None:
    now = dt.datetime(2026, 5, 26, 9, 30, tzinfo=dt.timezone.utc)
    weekly = build_weekly_options_screen(
        FixtureWeeklyScreenProvider(anchor_date=now.date()),
        WeeklyScreenRequest(market="US", top_n=3, historical_volatility=0.22),
        now=now,
    )
    packet = build_weekly_options_packet(
        weekly,
        FixtureOptionsResearchProvider(anchor_date=now.date()),
        now=now,
        agent_review_config=WeeklyAgentReviewConfig(enabled=False),
    )
    html_without_review = render_weekly_options_packet_html(packet)
    assert 'data-tab-target="agent-review"' not in html_without_review

    reviewed_packet = replace(
        packet,
        agent_review=WeeklyAgentReviewResult(
            model_used="deepseek/deepseek-v4-flash",
            fallback_used=False,
            synthesis="Synthesis",
            reflection="Reflection",
            deliberation="Deliberation",
            proposed_trading_idea="No action.",
            top_candidate={"rank": "1", "symbol": "US.AAPL", "option_code": "CODE", "reason": "Reason"},
            watchouts=["Watchout"],
            risk_controls=["Control"],
            follow_up_checks=["Check"],
            warnings=[],
            raw_response={},
        ),
    )
    html_with_review = render_weekly_options_packet_html(reviewed_packet)
    assert 'data-tab-target="agent-review"' in html_with_review
    assert "Portfolio-Level Synthesis" in html_with_review


def test_native_packet_sections_include_agent_review_sequentially_when_present() -> None:
    now = dt.datetime(2026, 5, 26, 9, 30, tzinfo=dt.timezone.utc)
    weekly = build_weekly_options_screen(
        FixtureWeeklyScreenProvider(anchor_date=now.date()),
        WeeklyScreenRequest(market="US", top_n=2, historical_volatility=0.22),
        now=now,
    )
    packet = build_weekly_options_packet(
        weekly,
        FixtureOptionsResearchProvider(anchor_date=now.date()),
        now=now,
        agent_review_config=WeeklyAgentReviewConfig(enabled=False),
    )
    sections_without_review = _native_packet_sections(packet)
    assert [section["title"] for section in sections_without_review[:2]] == ["Overview", "Top 10 Weekly Shortlist"]
    assert "Candidate Buckets" in [section["title"] for section in sections_without_review]
    assert "Agent Review" not in [section["title"] for section in sections_without_review]

    reviewed_packet = replace(
        packet,
        agent_review=WeeklyAgentReviewResult(
            model_used="deepseek/deepseek-v4-flash",
            fallback_used=True,
            synthesis="Synthesis",
            reflection="Reflection",
            deliberation="Deliberation",
            proposed_trading_idea="No action.",
            top_candidate={"rank": "1", "symbol": "US.AAPL", "option_code": "CODE", "reason": "Reason"},
            watchouts=["Watchout"],
            risk_controls=["Control"],
            follow_up_checks=["Check"],
            warnings=["primary failed"],
            raw_response={},
        ),
    )
    sections_with_review = _native_packet_sections(reviewed_packet)
    assert [section["title"] for section in sections_with_review[:3]] == [
        "Overview",
        "Top 10 Weekly Shortlist",
        "Agent Review",
    ]


def test_build_weekly_options_packet_uses_stock_first_methodology_language() -> None:
    now = dt.datetime(2026, 5, 26, 9, 30, tzinfo=dt.timezone.utc)
    weekly = build_weekly_options_screen(
        FixtureWeeklyScreenProvider(anchor_date=now.date()),
        WeeklyScreenRequest(market="US", top_n=3, historical_volatility=0.22),
        now=now,
    )

    packet = build_weekly_options_packet(
        weekly,
        FixtureOptionsResearchProvider(anchor_date=now.date()),
        now=now,
    )

    assert "stock-first" in packet.methodology_summary.lower()
    assert "trend regime" in packet.methodology_summary.lower()
