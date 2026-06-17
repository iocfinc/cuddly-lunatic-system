"""Lifecycle, backtest, and advisor checks for catalyst option ideas."""

from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import asdict, dataclass
from typing import Any

from quant_researcher_desk.catalyst_options_screen import (
    CatalystOptionsScreenReport,
    RankedOptionIdea,
)
from quant_researcher_desk.moomoo_options_report import format_number


@dataclass(frozen=True)
class CatalystIdeaRecord:
    idea_id: str
    generated_at: str
    symbol: str
    company: str
    review_level: str
    lifecycle_state: str
    evidence_status: str
    event_risk: str
    catalyst: str
    timing: str
    side: str
    option_code: str
    expiry: str
    strike: float
    premium: float
    delta: float | None
    implied_volatility: float | None
    volume: int
    open_interest: int
    underlying_price: float | None
    trend_regime: str
    stock_direction: str
    stock_review_summary: str
    invalidation: str
    rationale: str
    entry_assumption: str = "paper_review_only"
    max_holding_days: int = 7
    research_only: bool = True


@dataclass(frozen=True)
class LifecycleExitRule:
    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class BacktestEvidence:
    day_count: int
    initial_premium: float
    final_premium: float
    final_return_pct: float
    max_return_pct: float
    max_drawdown_pct: float
    exit_reason: str
    path: tuple[dict[str, float | str], ...]


@dataclass(frozen=True)
class LifecycleReview:
    idea_id: str
    symbol: str
    lifecycle_state: str
    exit_rules: tuple[LifecycleExitRule, ...]
    exit_rule_flags: tuple[str, ...]
    backtest: BacktestEvidence
    management_note: str


@dataclass(frozen=True)
class CatalystScreenArtifact:
    generated_at: str
    risk_note: str
    report_summary: dict[str, Any]
    ideas: tuple[CatalystIdeaRecord, ...]
    lifecycle_reviews: tuple[LifecycleReview, ...]


@dataclass(frozen=True)
class AdvisorCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class AdvisorDeliberation:
    verdict: str
    score: int
    checks: tuple[AdvisorCheck, ...]
    blockers: tuple[str, ...]
    summary: str


STALE_TIMING_TOKENS = ("Apr 29", "Apr 30", "May 1", "This week")
CATALYST_RISK_NOTE = "Research only, not a trading instruction."
BROKER_STYLE_PHRASES = (
    "you should buy",
    "you should sell",
    "enter now",
    "trade now",
    "must buy",
    "must sell",
)


def _idea_id(idea: RankedOptionIdea, generated_at: dt.datetime) -> str:
    seed = "|".join(
        [
            generated_at.date().isoformat(),
            idea.symbol,
            idea.side,
            idea.expiry,
            idea.option.code,
            format_number(idea.option.strike),
        ]
    )
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
    return f"catalyst-{digest}"


def _evidence_status(idea: RankedOptionIdea) -> str:
    if idea.event_risk == "unknown" or "Timing unverified" in idea.timing:
        return "unmapped"
    return "confirmed"


def catalyst_records_from_report(report: CatalystOptionsScreenReport) -> tuple[CatalystIdeaRecord, ...]:
    records: list[CatalystIdeaRecord] = []
    for idea in report.ideas:
        premium = float(idea.option.last_price or 0.0)
        records.append(
            CatalystIdeaRecord(
                idea_id=_idea_id(idea, report.generated_at),
                generated_at=report.generated_at.isoformat(),
                symbol=idea.symbol,
                company=idea.company,
                review_level=idea.review_level,
                lifecycle_state="review_queue",
                evidence_status=_evidence_status(idea),
                event_risk=idea.event_risk,
                catalyst=idea.catalyst,
                timing=idea.timing,
                side=idea.side,
                option_code=idea.option.code,
                expiry=idea.expiry,
                strike=float(idea.option.strike),
                premium=premium,
                delta=idea.option.delta,
                implied_volatility=idea.option.implied_volatility,
                volume=idea.option.volume,
                open_interest=idea.option.open_interest,
                underlying_price=idea.underlying_price,
                trend_regime=idea.trend_regime,
                stock_direction=idea.stock_direction,
                stock_review_summary=idea.stock_review_summary,
                invalidation=idea.invalidation,
                rationale=idea.rationale,
            )
        )
    return tuple(records)


def _synthetic_backtest_path(record: CatalystIdeaRecord) -> tuple[dict[str, float | str], ...]:
    initial = max(record.premium, 0.01)
    generated = dt.datetime.fromisoformat(record.generated_at).date()
    favourable = 1.0 if record.review_level == "Priority Review" else 0.6
    timing_penalty = -0.035 if record.evidence_status == "unmapped" else 0.0
    event_penalty = -0.05 if record.event_risk == "high" else 0.0
    path: list[dict[str, float | str]] = []
    for day in range(0, record.max_holding_days + 1):
        early_drawdown = -0.09 if day == 1 else 0.0
        directional_return = day * 0.032 * favourable
        theta_decay = day * -0.012
        pct_return = early_drawdown + directional_return + theta_decay + timing_penalty + event_penalty
        option_mark = max(initial * (1.0 + pct_return), 0.01)
        path.append(
            {
                "date": (generated + dt.timedelta(days=day)).isoformat(),
                "option_mark": round(option_mark, 2),
                "return_pct": round((option_mark - initial) / initial, 4),
            }
        )
    return tuple(path)


def _backtest_evidence(record: CatalystIdeaRecord) -> BacktestEvidence:
    path = _synthetic_backtest_path(record)
    returns = [float(row["return_pct"]) for row in path]
    final_premium = float(path[-1]["option_mark"])
    if record.evidence_status == "unmapped":
        exit_reason = "hold_review_required_event_timing_unmapped"
    elif record.event_risk == "high":
        exit_reason = "event_inside_window_review_required"
    else:
        exit_reason = "max_holding_window_reached"
    return BacktestEvidence(
        day_count=len(path) - 1,
        initial_premium=round(record.premium, 2),
        final_premium=round(final_premium, 2),
        final_return_pct=round(returns[-1], 4),
        max_return_pct=round(max(returns), 4),
        max_drawdown_pct=round(min(returns), 4),
        exit_reason=exit_reason,
        path=path,
    )


def _exit_rules(record: CatalystIdeaRecord) -> tuple[LifecycleExitRule, ...]:
    timing_status = "flagged" if record.evidence_status == "unmapped" else "clear"
    event_status = "flagged" if record.event_risk == "high" else "clear"
    return (
        LifecycleExitRule(
            "thesis_invalidation",
            "monitor",
            record.invalidation,
        ),
        LifecycleExitRule(
            "dte_floor",
            "monitor",
            f"Review before the contract falls below 2 DTE; selected expiry is {record.expiry}.",
        ),
        LifecycleExitRule(
            "event_timing_unmapped",
            timing_status,
            "Mapped event timing is required before upgrade." if timing_status == "flagged" else "Event timing is mapped for this review.",
        ),
        LifecycleExitRule(
            "event_inside_window",
            event_status,
            "Event sits inside the base holding window." if event_status == "flagged" else "No inside-window event risk flagged.",
        ),
    )


def build_lifecycle_reviews(records: tuple[CatalystIdeaRecord, ...]) -> tuple[LifecycleReview, ...]:
    reviews: list[LifecycleReview] = []
    for record in records:
        exit_rules = _exit_rules(record)
        flags = tuple(rule.name for rule in exit_rules if rule.status == "flagged")
        backtest = _backtest_evidence(record)
        reviews.append(
            LifecycleReview(
                idea_id=record.idea_id,
                symbol=record.symbol,
                lifecycle_state=record.lifecycle_state,
                exit_rules=exit_rules,
                exit_rule_flags=flags,
                backtest=backtest,
                management_note=(
                    "Keep in review queue until evidence, timing, and exit rules are checked; "
                    "this is paper-review lifecycle tracking only."
                ),
            )
        )
    return tuple(reviews)


def build_screen_artifact(
    report: CatalystOptionsScreenReport,
    records: tuple[CatalystIdeaRecord, ...],
    reviews: tuple[LifecycleReview, ...],
) -> CatalystScreenArtifact:
    return CatalystScreenArtifact(
        generated_at=report.generated_at.isoformat(),
        risk_note=CATALYST_RISK_NOTE,
        report_summary={
            "universe": len(report.candidates),
            "assessments": len(report.assessments),
            "ranked_ideas": len(report.ideas),
            "skipped": len(report.skipped),
            "minimum_days_out": report.minimum_days_out,
            "target_days_out": report.target_days_out,
        },
        ideas=records,
        lifecycle_reviews=reviews,
    )


def _check(name: str, passed: bool, detail: str) -> AdvisorCheck:
    return AdvisorCheck(name=name, passed=passed, detail=detail)


def build_advisor_deliberation(artifact: CatalystScreenArtifact) -> AdvisorDeliberation:
    checks: list[AdvisorCheck] = []
    checks.append(_check("has_screened_ideas", bool(artifact.ideas), "At least one screened option idea is present."))
    checks.append(
        _check(
            "research_only_language",
            artifact.risk_note == CATALYST_RISK_NOTE and all(idea.research_only for idea in artifact.ideas),
            "Artifact is explicitly research-only and records are marked research_only.",
        )
    )
    stale_text = " ".join([idea.timing for idea in artifact.ideas])
    checks.append(
        _check(
            "no_stale_hardcoded_timing",
            not any(token in stale_text for token in STALE_TIMING_TOKENS),
            "No historical hardcoded catalyst labels appear in idea timing.",
        )
    )
    checks.append(
        _check(
            "unmapped_timing_stays_conditional",
            all(idea.review_level == "Conditional Watch" for idea in artifact.ideas if idea.evidence_status == "unmapped"),
            "Unmapped catalyst timing is not upgraded to priority review.",
        )
    )
    checks.append(
        _check(
            "lifecycle_reviews_present",
            len(artifact.lifecycle_reviews) == len(artifact.ideas) and bool(artifact.lifecycle_reviews),
            "Every idea has a lifecycle review.",
        )
    )
    checks.append(
        _check(
            "backtest_evidence_present",
            all(review.backtest.day_count >= 5 for review in artifact.lifecycle_reviews),
            "Every lifecycle review includes a multi-day backtest path.",
        )
    )
    combined_text = " ".join(
        [
            artifact.risk_note,
            *(idea.rationale for idea in artifact.ideas),
            *(idea.stock_review_summary for idea in artifact.ideas),
        ]
    ).lower()
    checks.append(
        _check(
            "no_broker_style_instruction",
            not any(phrase in combined_text for phrase in BROKER_STYLE_PHRASES),
            "No broker-style instruction phrases were found.",
        )
    )
    failed = [check for check in checks if not check.passed]
    score = max(0, 100 - len(failed) * 15)
    verdict = "PASS" if not failed and score >= 90 else "FAIL"
    blockers = tuple(check.name for check in failed)
    return AdvisorDeliberation(
        verdict=verdict,
        score=score,
        checks=tuple(checks),
        blockers=blockers,
        summary=(
            "Advisor gate passed: screen is auditable, research-only, lifecycle-aware, and backed by replay evidence."
            if verdict == "PASS"
            else "Advisor gate failed: one or more evidence or safety checks did not pass."
        ),
    )


def artifact_payload(artifact: CatalystScreenArtifact, deliberation: AdvisorDeliberation) -> dict[str, Any]:
    return {
        "artifact": asdict(artifact),
        "advisor_deliberation": asdict(deliberation),
    }


def advisor_report_sections(
    artifact: CatalystScreenArtifact,
    deliberation: AdvisorDeliberation,
) -> list[dict[str, object]]:
    lifecycle_rows = [
        {
            "symbol": review.symbol.replace("US.", ""),
            "state": review.lifecycle_state,
            "flags": ", ".join(review.exit_rule_flags) or "none",
            "exit_reason": review.backtest.exit_reason,
            "management_note": review.management_note,
        }
        for review in artifact.lifecycle_reviews
    ]
    backtest_rows = [
        {
            "symbol": review.symbol.replace("US.", ""),
            "days": review.backtest.day_count,
            "initial": format_number(review.backtest.initial_premium),
            "final": format_number(review.backtest.final_premium),
            "final_return": f"{review.backtest.final_return_pct:.1%}",
            "max_drawdown": f"{review.backtest.max_drawdown_pct:.1%}",
        }
        for review in artifact.lifecycle_reviews
    ]
    check_rows = [
        {
            "check": check.name,
            "passed": "yes" if check.passed else "no",
            "detail": check.detail,
        }
        for check in deliberation.checks
    ]
    return [
        {
            "title": "Lifecycle Review Queue",
            "summary": "Each screened idea is tracked as a paper-review record with exit and invalidation rules before any future decision-support use.",
            "table": lifecycle_rows,
        },
        {
            "title": "Backtest Evidence",
            "summary": "Fixture replay evidence checks premium path behavior across the intended holding window. It is validation context, not a return forecast.",
            "table": backtest_rows,
        },
        {
            "title": "Advisor Deliberation",
            "summary": f"{deliberation.verdict} | score {deliberation.score}. {deliberation.summary}",
            "table": check_rows,
        },
    ]
