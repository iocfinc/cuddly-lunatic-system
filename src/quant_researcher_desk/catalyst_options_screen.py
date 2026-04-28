"""Catalyst-driven options screening for near-term earnings watches."""

from __future__ import annotations

import datetime as dt
import html
from dataclasses import dataclass
from typing import Protocol

from quant_researcher_desk.moomoo_options_report import (
    OptionsReportError,
    QuoteClient,
    build_options_report,
    format_number,
)
from quant_researcher_desk.moomoo_options_report import RankedOption as ChainOption


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
    underlying_price: float | None
    expiry: str
    option: ChainOption
    side: str
    score: float
    rationale: str
    beginner_note: str


@dataclass(frozen=True)
class CatalystOptionsScreenReport:
    generated_at: dt.datetime
    candidates: tuple[CatalystCandidate, ...]
    ideas: tuple[RankedOptionIdea, ...]
    skipped: tuple[str, ...]
    minimum_days_out: int = 5
    target_days_out: int = 7


class CatalystQuoteClient(QuoteClient, Protocol):
    pass


DEFAULT_CANDIDATES: tuple[CatalystCandidate, ...] = (
    CatalystCandidate("US.META", "Meta Platforms", "Mega-cap tech earnings; AI capex and ads read-through", "Apr 29", "Event options can move fast. Prefer liquid strikes near 25-45 delta."),
    CatalystCandidate("US.MSFT", "Microsoft", "Mega-cap tech earnings; Azure, Copilot, and AI monetization", "Apr 29", "Watch whether the premium is too rich versus the move needed after earnings."),
    CatalystCandidate("US.AMZN", "Amazon", "Mega-cap tech earnings; AWS growth and retail margin mix", "Apr 29", "Calls express upside, but puts can be cleaner if the market already expects strength."),
    CatalystCandidate("US.GOOGL", "Alphabet", "Mega-cap tech earnings; search, cloud, and AI capex debate", "Apr 29", "For beginners, avoid very far OTM strikes even when they look cheap."),
    CatalystCandidate("US.LRCX", "Lam Research", "Semicap earnings; wafer-fab equipment cycle and AI supply chain", "Apr 29", "Semicap names can gap hard; liquidity and spread matter as much as direction."),
    CatalystCandidate("US.AAPL", "Apple", "Earnings this week; China, services, and device cycle", "Apr 30", "A lower-delta call may look cheap, but the stock needs a bigger move to matter."),
    CatalystCandidate("US.LLY", "Eli Lilly", "Earnings this week; GLP-1 demand and guidance", "Apr 30", "High-priced underlyings can make contracts expensive; define max loss first."),
    CatalystCandidate("US.XOM", "Exxon Mobil", "Energy earnings; oil volatility and capital returns", "May 1", "Energy options can move with crude headlines before earnings arrives."),
    CatalystCandidate("US.CVX", "Chevron", "Energy earnings; oil volatility and capital returns", "May 1", "Prefer strikes with real volume; wide spreads can erase the thesis."),
    CatalystCandidate("US.KLAC", "KLA", "Semicap earnings surprise watch; process-control demand", "This week", "Use this as a supply-chain read-through, not a standalone prediction."),
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


def best_option(options: list[ChainOption], side: str) -> ChainOption | None:
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


def build_catalyst_options_screen(
    client: CatalystQuoteClient,
    candidates: tuple[CatalystCandidate, ...] = DEFAULT_CANDIDATES,
    now: dt.datetime | None = None,
    minimum_days_out: int = 5,
    target_days_out: int = 7,
) -> CatalystOptionsScreenReport:
    generated_at = now or dt.datetime.now(dt.timezone.utc).astimezone()
    ideas: list[RankedOptionIdea] = []
    skipped: list[str] = []
    for candidate in candidates:
        try:
            report = build_options_report(
                client,
                candidate.symbol,
                rows=12,
                now=generated_at,
                minimum_days_out=minimum_days_out,
                target_days_out=target_days_out,
            )
        except Exception as exc:
            skipped.append(f"{candidate.symbol}: {exc}")
            continue

        call = best_option(report.calls, "Call")
        put = best_option(report.puts, "Put")
        for side, option in (("Call", call), ("Put", put)):
            if option is None:
                continue
            ideas.append(
                RankedOptionIdea(
                    symbol=candidate.symbol,
                    company=candidate.company,
                    catalyst=candidate.catalyst,
                    timing=candidate.timing,
                    underlying_price=report.underlying_price,
                    expiry=report.expiry,
                    option=option,
                    side=side,
                    score=option_score(option),
                    rationale=option_rationale(option, side),
                    beginner_note=candidate.beginner_note,
                )
            )
    return CatalystOptionsScreenReport(
        generated_at=generated_at,
        candidates=candidates,
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
            "side": idea.side,
            "strike": format_number(idea.option.strike),
            "expiry": idea.expiry,
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
    best_by_symbol: dict[str, RankedOptionIdea] = {}
    for idea in report.ideas:
        best_by_symbol.setdefault(idea.symbol, idea)
    return [
        {
            "symbol": candidate.symbol.replace("US.", ""),
            "company": candidate.company,
            "catalyst": candidate.catalyst,
            "timing": candidate.timing,
            "top_option": (
                f"{best_by_symbol[candidate.symbol].side} {format_number(best_by_symbol[candidate.symbol].option.strike)}"
                if candidate.symbol in best_by_symbol
                else "No liquid candidate"
            ),
            "beginner_read": candidate.beginner_note,
        }
        for candidate in report.candidates
    ]


def catalyst_report_sections(report: CatalystOptionsScreenReport) -> list[dict[str, object]]:
    top_rows = idea_rows(report, limit=20)
    call_count = sum(1 for idea in report.ideas[:20] if idea.side == "Call")
    put_count = sum(1 for idea in report.ideas[:20] if idea.side == "Put")
    return [
        {
            "title": "Desk Summary",
            "content": (
                f"This screen is deliberately proactive: it ignores same-day expiry noise and targets contracts about "
                f"{report.target_days_out} days out, with a minimum window of {report.minimum_days_out} days. The filter starts "
                "with upcoming earnings/catalysts, then asks whether the option has enough liquidity and a readable delta. "
                "For a beginner, that matters because cheap contracts are often cheap for a reason: low probability, poor "
                "liquidity, or too much implied volatility."
            ),
        },
        {
            "title": "Catalyst Watchlist",
            "table": company_rows(report),
        },
        {
            "title": "Ranked Option Ideas",
            "summary": "Higher rank means better liquidity plus a delta profile that is easier to reason about around an event.",
            "table": top_rows,
        },
        {
            "title": "Call vs Put Mix",
            "summary": "This is a quick visual check of whether the screen is finding more upside or downside expressions.",
            "chart": {"rows": [{"label": "Calls", "value": call_count}, {"label": "Puts", "value": put_count}]},
        },
        {
            "title": "Learning Corner",
            "content": (
                "Skill used: event-options screening. Step 1: find a catalyst that can move the stock. Step 2: avoid illiquid contracts. "
                "Step 3: choose enough time for a thesis to develop; same-day expiry is usually reaction trading, not research. "
                "Step 4: use delta as a rough probability/exposure guide. A 0.30 delta call is not a prediction that the stock goes up; "
                "it is a contract that needs a meaningful move to become useful. Step 5: compare premium with the move required. "
                "If the option costs too much, being directionally right can still lose money."
            ),
        },
        {
            "title": "Risk Notes",
            "items": [
                "Earnings options can lose value immediately after the event because implied volatility often collapses.",
                "The screen avoids same-day expiries; if no contract is available at least several days out, the ticker is skipped.",
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
            f"{index}. <b>{html.escape(idea.symbol.replace('US.', ''))}</b> {html.escape(idea.side)} "
            f"<code>{format_number(idea.option.strike)}</code> exp <code>{html.escape(idea.expiry)}</code> "
            f"Δ <code>{format_number(idea.option.delta, 3)}</code>"
        )
    lines.extend(["", "PDF attached. Research only, not a trading instruction."])
    return "\n".join(lines)
