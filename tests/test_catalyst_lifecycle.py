from __future__ import annotations

import datetime as dt
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quant_researcher_desk.catalyst_lifecycle import (
    advisor_report_sections,
    build_advisor_deliberation,
    build_lifecycle_reviews,
    build_screen_artifact,
    catalyst_records_from_report,
)
from quant_researcher_desk.catalyst_options_screen import (
    DEFAULT_CANDIDATES,
    FixtureCatalystOptionsProvider,
    build_catalyst_options_screen,
)


def _fixture_report():
    now = dt.datetime(2026, 6, 17, 9, 30, tzinfo=dt.timezone.utc)
    provider = FixtureCatalystOptionsProvider(anchor_date=now.date())
    return build_catalyst_options_screen(provider, DEFAULT_CANDIDATES, now=now)


def test_catalyst_idea_records_capture_evidence_and_lifecycle_state() -> None:
    report = _fixture_report()

    records = catalyst_records_from_report(report)

    assert records
    assert all(record.idea_id.startswith("catalyst-") for record in records)
    assert all(record.lifecycle_state == "review_queue" for record in records)
    assert all(record.research_only is True for record in records)
    assert all(record.entry_assumption == "paper_review_only" for record in records)
    assert {record.evidence_status for record in records} <= {"confirmed", "unmapped"}
    assert any(record.evidence_status == "unmapped" for record in records)
    assert any(record.evidence_status == "confirmed" for record in records)


def test_lifecycle_reviews_include_backtest_stats_and_exit_rule_flags() -> None:
    report = _fixture_report()
    records = catalyst_records_from_report(report)

    reviews = build_lifecycle_reviews(records)

    assert len(reviews) == len(records)
    assert all(review.backtest.day_count >= 5 for review in reviews)
    assert all(review.exit_rules for review in reviews)
    assert all(review.backtest.max_drawdown_pct <= 0 for review in reviews)
    assert any("event_timing_unmapped" in review.exit_rule_flags for review in reviews)
    assert any(review.backtest.final_return_pct > 0 for review in reviews)


def test_advisor_deliberation_passes_complete_research_only_artifact() -> None:
    report = _fixture_report()
    records = catalyst_records_from_report(report)
    reviews = build_lifecycle_reviews(records)
    artifact = build_screen_artifact(report, records, reviews)

    deliberation = build_advisor_deliberation(artifact)

    assert deliberation.verdict == "PASS"
    assert deliberation.score >= 90
    assert not deliberation.blockers
    assert any("research_only_language" in check.name for check in deliberation.checks)
    assert "Research only, not a trading instruction." in artifact.risk_note


def test_advisor_report_sections_surface_lifecycle_and_backtest_context() -> None:
    report = _fixture_report()
    records = catalyst_records_from_report(report)
    reviews = build_lifecycle_reviews(records)
    artifact = build_screen_artifact(report, records, reviews)
    deliberation = build_advisor_deliberation(artifact)

    sections = advisor_report_sections(artifact, deliberation)
    titles = {str(section["title"]) for section in sections}

    assert "Advisor Deliberation" in titles
    assert "Lifecycle Review Queue" in titles
    assert "Backtest Evidence" in titles
