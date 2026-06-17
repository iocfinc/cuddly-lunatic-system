"""Catalyst-driven options screening for near-term earnings watches."""

from __future__ import annotations

import datetime as dt
import html
from dataclasses import dataclass
from typing import Protocol

from quant_researcher_desk.moomoo_options_report import (
    QuoteClient,
    build_options_report,
    format_number,
)
from quant_researcher_desk.moomoo_options_report import RankedOption as ChainOption
from quant_researcher_desk.options_research import EarningsContext, classify_event_risk, get_earnings_context
from quant_researcher_desk.stock_context import StockReviewResult, build_stock_context, fallback_stock_review
from quant_researcher_desk.fixture_options_market import (
    fixture_daily_bars,
    fixture_expiries,
    fixture_market_snapshots,
    fixture_option_chain,
    fixture_spot,
)


@dataclass(frozen=True)
class CatalystCandidate:
    symbol: str
    company: str
    catalyst: str
    timing: str
    beginner_note: str


@dataclass(frozen=True)
class RankedOptionIdea:
    symbol: str
    company: str
    catalyst: str
    timing: str
    event_risk: str
    underlying_price: float | None
    expiry: str
    option: ChainOption
    side: str
    score: float
    trend_regime: str
    stock_direction: str
    review_level: str
    rationale: str
    stock_review_summary: str
    invalidation: str
    beginner_note: str


@dataclass(frozen=True)
class CatalystOptionsScreenReport:
    generated_at: dt.datetime
    candidates: tuple[CatalystCandidate, ...]
    assessments: tuple["CandidateAssessment", ...]
    ideas: tuple[RankedOptionIdea, ...]
    skipped: tuple[str, ...]
    minimum_days_out: int = 5
    target_days_out: int = 7


@dataclass(frozen=True)
class CandidateAssessment:
    symbol: str
    company: str
    catalyst: str
    timing: str
    trend_regime: str
    stock_direction: str
    event_risk: str
    review_level: str
    top_option: str
    note: str
    beginner_note: str


class CatalystQuoteClient(QuoteClient, Protocol):
    pass


class FixtureCatalystOptionsProvider:
    """Deterministic provider for full catalyst screen runs without OpenD."""

    def __init__(self, anchor_date: dt.date | None = None) -> None:
        self.anchor_date = anchor_date or dt.date(2026, 6, 17)

    def get_underlying_snapshot(self, symbol: str) -> dict[str, object]:
        return {"code": symbol, "last_price": fixture_spot(symbol)}

    def get_option_expirations(self, symbol: str) -> list[str]:
        del symbol
        return fixture_expiries(self.anchor_date)

    def get_option_chain(self, symbol: str, expiry: str) -> list[dict[str, object]]:
        return fixture_option_chain(symbol, expiry)

    def get_market_snapshots(self, codes: list[str]) -> list[dict[str, object]]:
        return fixture_market_snapshots(codes)

    def get_daily_bars(self, symbol: str, count: int = 250) -> list[dict[str, object]]:
        return fixture_daily_bars(symbol, count=count)

    def get_earnings_context(self, symbol: str) -> EarningsContext:
        if symbol in {"US.META", "US.AAPL", "US.KLAC"}:
            return EarningsContext(
                next_date=(self.anchor_date + dt.timedelta(days=14)).isoformat(),
                phase="post-window",
                summary="Fixture event context: mapped date sits outside the base weekly holding window.",
                risk_level="low",
                within_holding_window=False,
                source="fixture",
            )
        if symbol == "US.LLY":
            return EarningsContext(
                next_date=(self.anchor_date + dt.timedelta(days=3)).isoformat(),
                phase="pre-earnings",
                summary="Fixture event context: mapped date sits inside the weekly holding window.",
                risk_level="high",
                within_holding_window=True,
                source="fixture",
            )
        return EarningsContext(
            next_date=None,
            phase="unknown",
            summary="Fixture event context: timing is intentionally unmapped for this name.",
            risk_level="unknown",
            within_holding_window=None,
            source="fixture",
        )

    def close(self) -> None:
        return None


UNVERIFIED_TIMING_NOTE = "Timing unverified; confirm the next event date with a live source."


DEFAULT_CANDIDATES: tuple[CatalystCandidate, ...] = (
    CatalystCandidate("US.META", "Meta Platforms", "Mega-cap tech earnings watch; confirm the next date live before treating it as a catalyst lane.", UNVERIFIED_TIMING_NOTE, "Event options can move fast. Prefer liquid strikes near 25-45 delta."),
    CatalystCandidate("US.MSFT", "Microsoft", "Mega-cap tech earnings watch; confirm the next date live before treating it as a catalyst lane.", UNVERIFIED_TIMING_NOTE, "Watch whether the premium is too rich versus the move needed after earnings."),
    CatalystCandidate("US.AMZN", "Amazon", "Mega-cap tech earnings watch; confirm the next date live before treating it as a catalyst lane.", UNVERIFIED_TIMING_NOTE, "Calls express upside, but puts can be cleaner if the market already expects strength."),
    CatalystCandidate("US.GOOGL", "Alphabet", "Mega-cap tech earnings watch; confirm the next date live before treating it as a catalyst lane.", UNVERIFIED_TIMING_NOTE, "For beginners, avoid very far OTM strikes even when they look cheap."),
    CatalystCandidate("US.LRCX", "Lam Research", "Semicap earnings and AI supply-chain watch; confirm the next date live before treating it as a catalyst lane.", UNVERIFIED_TIMING_NOTE, "Semicap names can gap hard; liquidity and spread matter as much as direction."),
    CatalystCandidate("US.AAPL", "Apple", "Apple earnings watch; confirm the next date live before treating it as a catalyst lane.", UNVERIFIED_TIMING_NOTE, "A lower-delta call may look cheap, but the stock needs a bigger move to matter."),
    CatalystCandidate("US.LLY", "Eli Lilly", "Large-cap healthcare earnings watch; confirm the next date live before treating it as a catalyst lane.", UNVERIFIED_TIMING_NOTE, "High-priced underlyings can make contracts expensive; define max loss first."),
    CatalystCandidate("US.XOM", "Exxon Mobil", "Energy earnings and crude-sensitivity watch; confirm the next date live before treating it as a catalyst lane.", UNVERIFIED_TIMING_NOTE, "Energy options can move with crude headlines before earnings arrives."),
    CatalystCandidate("US.CVX", "Chevron", "Energy earnings and crude-sensitivity watch; confirm the next date live before treating it as a catalyst lane.", UNVERIFIED_TIMING_NOTE, "Prefer strikes with real volume; wide spreads can erase the thesis."),
    CatalystCandidate("US.KLAC", "KLA", "Semicap earnings watch; confirm the next date live before treating it as a catalyst lane.", UNVERIFIED_TIMING_NOTE, "Use this as a supply-chain read-through, not a standalone prediction."),
)


def option_score(option: ChainOption) -> float:
    delta = abs(option.delta or 0.0)
    delta_quality = max(0.0, 1.0 - abs(delta - 0.35) / 0.35)
    liquidity = option.volume * 1.0 + option.open_interest * 0.08
    price_penalty = 0.0 if option.last_price and option.last_price > 0 else -500.0
    return liquidity + delta_quality * 250 + price_penalty


def option_rationale(option: ChainOption, side: str) -> str:
    delta = abs(option.delta or 0.0)
    iv = option.implied_volatility
    parts = [
        f"{side} candidate with {option.volume:,} volume and {option.open_interest:,} open interest.",
        f"Delta near {delta:.2f} gives a readable event-risk profile for a beginner screen.",
    ]
    if iv is not None:
        parts.append(f"IV is {iv:.1f}; treat that as premium temperature, not a forecast.")
    if option.last_price is not None:
        parts.append(f"Premium is {option.last_price:.2f}; this is the max loss for a long option before fees/slippage.")
    return " ".join(parts)


def best_option(options: list[ChainOption]) -> ChainOption | None:
    liquid = [
        option
        for option in options
        if option.last_price is not None
        and option.last_price > 0
        and option.volume >= 25
        and option.open_interest >= 100
        and 0.15 <= abs(option.delta or 0.0) <= 0.65
    ]
    if not liquid:
        liquid = [option for option in options if option.last_price is not None and option.last_price > 0]
    if not liquid:
        return None
    return max(liquid, key=option_score)


def _load_stock_review(client: CatalystQuoteClient, candidate: CatalystCandidate) -> StockReviewResult:
    rows = client.get_daily_bars(candidate.symbol, count=250)
    context = build_stock_context(candidate.symbol, rows)
    return fallback_stock_review(context)


def _resolved_timing(candidate: CatalystCandidate, earnings: EarningsContext) -> str:
    if earnings.next_date:
        window = "inside holding window" if earnings.within_holding_window is True else "outside holding window"
        if earnings.within_holding_window is None:
            window = earnings.phase or "mapped"
        return f"{earnings.next_date} ({window}; source={earnings.source})"
    return candidate.timing


def _review_level(stock_review: StockReviewResult, event_risk: str, option: ChainOption | None) -> str:
    if stock_review.direction == "no_trade" or option is None:
        return "Pass"
    if event_risk in {"low", "medium"}:
        return "Priority Review"
    return "Conditional Watch"


def _assessment_note(stock_review: StockReviewResult, event_risk: str, option: ChainOption | None) -> str:
    if stock_review.direction == "no_trade":
        return stock_review.thesis_summary
    if option is None:
        return "No aligned option contract passed the liquidity and delta filters."
    if event_risk == "high":
        return "Mapped event sits inside the intended holding window, so keep this as a conditional review only."
    if event_risk == "medium":
        return "Mapped event is nearby but not cleanly inside the base holding window; manual review is still required."
    if event_risk == "low":
        return "Stock regime and mapped timing are clean enough for first-pass human review."
    return "Stock regime is aligned, but catalyst timing is unverified in the current provider lane."


def _score_adjustment_for_event_risk(event_risk: str) -> float:
    if event_risk == "low":
        return 75.0
    if event_risk == "medium":
        return 25.0
    if event_risk == "high":
        return -50.0
    return -25.0


def build_catalyst_options_screen(
    client: CatalystQuoteClient,
    candidates: tuple[CatalystCandidate, ...] = DEFAULT_CANDIDATES,
    now: dt.datetime | None = None,
    minimum_days_out: int = 5,
    target_days_out: int = 7,
) -> CatalystOptionsScreenReport:
    generated_at = now or dt.datetime.now(dt.timezone.utc).astimezone()
    assessments: list[CandidateAssessment] = []
    ideas: list[RankedOptionIdea] = []
    skipped: list[str] = []
    for candidate in candidates:
        earnings = get_earnings_context(client, candidate.symbol)
        timing = _resolved_timing(candidate, earnings)
        event_risk = classify_event_risk(earnings)
        try:
            stock_review = _load_stock_review(client, candidate)
            aligned_side = "Call" if stock_review.direction == "bullish" else "Put"
            if stock_review.direction == "no_trade":
                note = _assessment_note(stock_review, event_risk, None)
                assessments.append(
                    CandidateAssessment(
                        symbol=candidate.symbol,
                        company=candidate.company,
                        catalyst=candidate.catalyst,
                        timing=timing,
                        trend_regime=stock_review.trend_regime,
                        stock_direction=stock_review.direction,
                        event_risk=event_risk,
                        review_level="Pass",
                        top_option="Skip mixed or unresolved stock regime",
                        note=note,
                        beginner_note=candidate.beginner_note,
                    )
                )
                skipped.append(f"{candidate.symbol}: stock-first gate blocked a mixed or no-trade regime.")
                continue
            report = build_options_report(
                client,
                candidate.symbol,
                rows=12,
                now=generated_at,
                minimum_days_out=minimum_days_out,
                target_days_out=target_days_out,
            )
        except Exception as exc:
            assessments.append(
                CandidateAssessment(
                    symbol=candidate.symbol,
                    company=candidate.company,
                    catalyst=candidate.catalyst,
                    timing=timing,
                    trend_regime="unknown",
                    stock_direction="unknown",
                    event_risk=event_risk,
                    review_level="Pass",
                    top_option="Unavailable",
                    note=str(exc),
                    beginner_note=candidate.beginner_note,
                )
            )
            skipped.append(f"{candidate.symbol}: {exc}")
            continue

        option = best_option(report.calls if aligned_side == "Call" else report.puts)
        review_level = _review_level(stock_review, event_risk, option)
        note = _assessment_note(stock_review, event_risk, option)
        top_option = f"{aligned_side} {format_number(option.strike)}" if option is not None else "No aligned liquid candidate"
        assessments.append(
            CandidateAssessment(
                symbol=candidate.symbol,
                company=candidate.company,
                catalyst=candidate.catalyst,
                timing=timing,
                trend_regime=stock_review.trend_regime,
                stock_direction=stock_review.direction,
                event_risk=event_risk,
                review_level=review_level,
                top_option=top_option,
                note=note,
                beginner_note=candidate.beginner_note,
            )
        )
        if option is None:
            skipped.append(f"{candidate.symbol}: no aligned liquid {aligned_side.upper()} contract passed the catalyst filters.")
            continue
        ideas.append(
            RankedOptionIdea(
                symbol=candidate.symbol,
                company=candidate.company,
                catalyst=candidate.catalyst,
                timing=timing,
                event_risk=event_risk,
                underlying_price=report.underlying_price,
                expiry=report.expiry,
                option=option,
                side=aligned_side,
                score=option_score(option) + _score_adjustment_for_event_risk(event_risk),
                trend_regime=stock_review.trend_regime,
                stock_direction=stock_review.direction,
                review_level=review_level,
                rationale=option_rationale(option, aligned_side),
                stock_review_summary=stock_review.thesis_summary,
                invalidation=stock_review.invalidation,
                beginner_note=candidate.beginner_note,
            )
        )
    return CatalystOptionsScreenReport(
        generated_at=generated_at,
        candidates=candidates,
        assessments=tuple(assessments),
        ideas=tuple(sorted(ideas, key=lambda idea: idea.score, reverse=True)),
        skipped=tuple(skipped),
        minimum_days_out=minimum_days_out,
        target_days_out=target_days_out,
    )


def idea_rows(report: CatalystOptionsScreenReport, limit: int = 20) -> list[dict[str, object]]:
    return [
        {
            "rank": index,
            "symbol": idea.symbol.replace("US.", ""),
            "review_level": idea.review_level,
            "side": idea.side,
            "strike": format_number(idea.option.strike),
            "expiry": idea.expiry,
            "trend": idea.trend_regime,
            "event_risk": idea.event_risk,
            "premium": format_number(idea.option.last_price),
            "delta": format_number(idea.option.delta, 3),
            "iv": format_number(idea.option.implied_volatility),
            "volume": f"{idea.option.volume:,}",
            "open_interest": f"{idea.option.open_interest:,}",
            "why_it_matters": idea.catalyst,
        }
        for index, idea in enumerate(report.ideas[:limit], start=1)
    ]


def company_rows(report: CatalystOptionsScreenReport) -> list[dict[str, object]]:
    return [
        {
            "symbol": assessment.symbol.replace("US.", ""),
            "company": assessment.company,
            "review_level": assessment.review_level,
            "trend": assessment.trend_regime,
            "event_risk": assessment.event_risk,
            "catalyst": assessment.catalyst,
            "timing": assessment.timing,
            "top_option": assessment.top_option,
            "note": assessment.note,
            "beginner_read": assessment.beginner_note,
        }
        for assessment in report.assessments
    ]


def catalyst_report_sections(report: CatalystOptionsScreenReport) -> list[dict[str, object]]:
    top_rows = idea_rows(report, limit=20)
    call_count = sum(1 for idea in report.ideas[:20] if idea.side == "Call")
    put_count = sum(1 for idea in report.ideas[:20] if idea.side == "Put")
    return [
        {
            "title": "Desk Summary",
            "content": (
                f"This screen now runs stock-first: it checks the trend regime before picking an option and only keeps the aligned "
                f"CALL or PUT side roughly {report.target_days_out} days out, with a minimum window of {report.minimum_days_out} days. "
                "The candidate universe is a maintained product watchlist, not a live event feed, so timing stays conditional unless "
                "a provider supplies mapped earnings context."
            ),
        },
        {
            "title": "Catalyst Watchlist Status",
            "table": company_rows(report),
        },
        {
            "title": "Ranked Option Ideas",
            "summary": "Higher rank means the stock regime aligned first, then the contract survived liquidity and delta checks. Unknown event timing stays conditional.",
            "table": top_rows,
        },
        {
            "title": "Call vs Put Mix",
            "summary": "This is a quick visual check of how many aligned bullish versus bearish expressions survived the stock-first gate.",
            "chart": {"rows": [{"label": "Calls", "value": call_count}, {"label": "Puts", "value": put_count}]},
        },
        {
            "title": "Learning Corner",
            "content": (
                "Step 1: confirm the stock has a clean bullish or bearish regime. Step 2: if the regime is mixed, do not force a contract. "
                "Step 3: only review the aligned CALL or PUT side after liquidity and delta checks. Step 4: treat live event timing as a required source, "
                "not a guessed label. Step 5: if timing is unmapped, keep the name in a conditional watch bucket instead of upgrading it to a priority review."
            ),
        },
        {
            "title": "Risk Notes",
            "items": [
                "Earnings options can lose value immediately after the event because implied volatility often collapses.",
                "The screen avoids same-day expiries; if no aligned contract is available at least several days out, the ticker is skipped.",
                "Event timing is provider-optional in this lane today, so unmapped names must stay conditional rather than pretending the catalyst is current.",
                "This workflow does not use Yahoo Finance or news feeds in deterministic scoring; candidate themes are watchlist notes until a source is wired in.",
                "High volume does not guarantee a good trade; it only says the contract is active.",
                "Beginners should define max loss before entry and avoid oversized event bets.",
                *(list(report.skipped) if report.skipped else []),
            ],
        },
    ]


def format_catalyst_telegram_html(report: CatalystOptionsScreenReport) -> str:
    top = report.ideas[:5]
    lines = [
        "<b>📊 Catalyst Options Screen</b>",
        report.generated_at.strftime("<code>%Y-%m-%d %H:%M %Z</code>").strip(),
        "",
        f"Universe: <code>{len(report.candidates)} names</code> | Ranked ideas: <code>{len(report.ideas)}</code>",
        f"Expiry lens: <code>~{report.target_days_out}D out</code>, minimum <code>{report.minimum_days_out}D</code>",
        "",
    ]
    for index, idea in enumerate(top, start=1):
        lines.append(
            f"{index}. <b>{html.escape(idea.symbol.replace('US.', ''))}</b> {html.escape(idea.review_level)} | {html.escape(idea.side)} "
            f"<code>{format_number(idea.option.strike)}</code> exp <code>{html.escape(idea.expiry)}</code> "
            f"Δ <code>{format_number(idea.option.delta, 3)}</code>"
        )
    lines.extend(["", "Mapped timing is optional in this lane; unmapped names stay conditional.", "PDF attached. Research only, not a trading instruction."])
    return "\n".join(lines)
