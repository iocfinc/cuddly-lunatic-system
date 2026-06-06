"""Shared execution recovery policy for multi-symbol research flows."""

from __future__ import annotations

import dataclasses
import time
from collections import Counter
from dataclasses import dataclass
from typing import Callable, TypeVar

from quant_researcher_desk.moomoo_options_report import OptionsReportError

ReasonCode = str

REASON_NOT_OPTIONABLE = "not_optionable"
REASON_NO_EXPIRATIONS = "no_expirations"
REASON_EMPTY_CHAIN = "empty_chain"
REASON_MISSING_DAILY_BARS = "missing_daily_bars"
REASON_MISSING_UNDERLYING_SNAPSHOT = "missing_underlying_snapshot"
REASON_MISSING_CONTRACT_SNAPSHOT = "missing_contract_snapshot"
REASON_NO_CONTRACT_MATCH = "no_contract_match"
REASON_MIXED_TREND_REGIME = "mixed_trend_regime"
REASON_STOCK_REVIEW_NO_TRADE = "stock_review_no_trade"
REASON_STOCK_REVIEW_FAILED = "stock_review_failed"
REASON_PROVIDER_RATE_LIMITED = "provider_rate_limited"
REASON_PROVIDER_UNREACHABLE = "provider_unreachable"
REASON_DEBATE_BACKEND_FAILED = "debate_backend_failed"
REASON_UNKNOWN = "unknown"

RECOVERABLE_REASON_CODES = {
    REASON_NOT_OPTIONABLE,
    REASON_NO_EXPIRATIONS,
    REASON_EMPTY_CHAIN,
    REASON_MISSING_DAILY_BARS,
    REASON_MISSING_UNDERLYING_SNAPSHOT,
    REASON_MISSING_CONTRACT_SNAPSHOT,
    REASON_NO_CONTRACT_MATCH,
    REASON_MIXED_TREND_REGIME,
    REASON_STOCK_REVIEW_NO_TRADE,
    REASON_STOCK_REVIEW_FAILED,
    REASON_PROVIDER_RATE_LIMITED,
    REASON_PROVIDER_UNREACHABLE,
    REASON_DEBATE_BACKEND_FAILED,
}

TRANSIENT_REASON_CODES = {
    REASON_PROVIDER_RATE_LIMITED,
    REASON_PROVIDER_UNREACHABLE,
}

OPTIONABILITY_REASON_CODES = {
    REASON_NOT_OPTIONABLE,
    REASON_NO_EXPIRATIONS,
    REASON_EMPTY_CHAIN,
    REASON_MISSING_DAILY_BARS,
    REASON_MISSING_UNDERLYING_SNAPSHOT,
    REASON_MISSING_CONTRACT_SNAPSHOT,
    REASON_NO_CONTRACT_MATCH,
    REASON_MIXED_TREND_REGIME,
    REASON_STOCK_REVIEW_NO_TRADE,
    REASON_STOCK_REVIEW_FAILED,
}

PROVIDER_REASON_CODES = {
    REASON_PROVIDER_RATE_LIMITED,
    REASON_PROVIDER_UNREACHABLE,
}

DEBATE_REASON_CODES = {REASON_DEBATE_BACKEND_FAILED}

_T = TypeVar("_T")


@dataclass(frozen=True)
class SymbolSkip:
    symbol: str
    stage: str
    reason_code: ReasonCode
    detail: str
    attempts: int = 1
    transient: bool = False

    @property
    def bucket(self) -> str:
        if self.reason_code in OPTIONABILITY_REASON_CODES:
            return "skipped_optionability"
        if self.reason_code in PROVIDER_REASON_CODES:
            return "skipped_provider"
        if self.reason_code in DEBATE_REASON_CODES:
            return "skipped_debate_backend"
        return "skipped_unknown"


@dataclass(frozen=True)
class SymbolExecutionError(Exception):
    symbol: str
    stage: str
    reason_code: ReasonCode
    detail: str
    attempts: int = 1
    transient: bool = False

    @property
    def recoverable_in_multi_symbol(self) -> bool:
        return self.reason_code in RECOVERABLE_REASON_CODES

    @property
    def skip(self) -> SymbolSkip:
        return SymbolSkip(
            symbol=self.symbol,
            stage=self.stage,
            reason_code=self.reason_code,
            detail=self.detail,
            attempts=self.attempts,
            transient=self.transient,
        )

    def single_symbol_message(self) -> str:
        headline = {
            REASON_NOT_OPTIONABLE: "requested symbol is not optionable today",
            REASON_NO_EXPIRATIONS: "no expirations returned for the requested symbol",
            REASON_EMPTY_CHAIN: "option chain returned no usable rows",
            REASON_MISSING_DAILY_BARS: "daily price history was missing",
            REASON_MISSING_UNDERLYING_SNAPSHOT: "underlying snapshot was missing",
            REASON_MISSING_CONTRACT_SNAPSHOT: "contract snapshot data was missing",
            REASON_NO_CONTRACT_MATCH: "no matching contract survived filters",
            REASON_MIXED_TREND_REGIME: "trend regime was mixed",
            REASON_STOCK_REVIEW_NO_TRADE: "stock review did not clear a directional thesis",
            REASON_STOCK_REVIEW_FAILED: "stock review failed",
            REASON_PROVIDER_RATE_LIMITED: "provider rate-limited the request",
            REASON_PROVIDER_UNREACHABLE: "provider was unreachable",
            REASON_DEBATE_BACKEND_FAILED: "debate backend failed",
        }.get(self.reason_code, "symbol execution failed")
        return f"{headline} at stage={self.stage} for {self.symbol}. {self.detail}"

    def __str__(self) -> str:
        return f"{self.symbol} stage={self.stage} reason={self.reason_code}: {self.detail}"


def make_symbol_error(
    symbol: str,
    stage: str,
    reason_code: ReasonCode,
    detail: str,
    *,
    attempts: int = 1,
    transient: bool | None = None,
) -> SymbolExecutionError:
    return SymbolExecutionError(
        symbol=symbol,
        stage=stage,
        reason_code=reason_code,
        detail=detail,
        attempts=attempts,
        transient=(reason_code in TRANSIENT_REASON_CODES) if transient is None else transient,
    )


def normalize_options_report_error(symbol: str, stage: str, exc: OptionsReportError) -> SymbolExecutionError:
    detail = str(exc).strip() or exc.__class__.__name__
    text = detail.lower()
    if "high frequency" in text or "rate limit" in text:
        reason_code = REASON_PROVIDER_RATE_LIMITED
    elif "cannot connect to opend" in text or "timed out" in text or "connection refused" in text:
        reason_code = REASON_PROVIDER_UNREACHABLE
    elif "opend failed to" in text:
        reason_code = REASON_PROVIDER_UNREACHABLE
    elif "not optionable" in text:
        reason_code = REASON_NOT_OPTIONABLE
    elif "no option expirations returned" in text or "no future option expirations" in text:
        reason_code = REASON_NO_EXPIRATIONS
    elif "at least" in text and "option expirations" in text:
        reason_code = REASON_NO_EXPIRATIONS
    elif "no option chain rows returned" in text:
        reason_code = REASON_EMPTY_CHAIN
    elif "daily bars" in text or "daily closes" in text or "trend regime" in text:
        reason_code = REASON_MISSING_DAILY_BARS
    elif "no underlying snapshot returned" in text or "no underlying price available" in text:
        reason_code = REASON_MISSING_UNDERLYING_SNAPSHOT
    elif "no option contract snapshots returned" in text or "no option contract snapshots produced usable contracts" in text:
        reason_code = REASON_MISSING_CONTRACT_SNAPSHOT
    elif "requested option code was not found" in text or "no contract matched the requested option filters" in text:
        reason_code = REASON_NO_CONTRACT_MATCH
    else:
        reason_code = REASON_UNKNOWN
    return make_symbol_error(symbol, stage, reason_code, detail)


def normalize_debate_backend_error(symbol: str, stage: str, exc: Exception) -> SymbolExecutionError:
    detail = str(exc).strip() or exc.__class__.__name__
    return make_symbol_error(symbol, stage, REASON_DEBATE_BACKEND_FAILED, detail, transient=False)


def with_symbol_retry(
    symbol: str,
    stage: str,
    operation: Callable[[], _T],
    *,
    max_attempts: int = 2,
    backoff_seconds: float = 0.2,
) -> _T:
    attempts = 0
    while True:
        attempts += 1
        try:
            return operation()
        except SymbolExecutionError as exc:
            issue = dataclasses.replace(exc, attempts=attempts)
        except OptionsReportError as exc:
            issue = dataclasses.replace(normalize_options_report_error(symbol, stage, exc), attempts=attempts)
        if not issue.transient or attempts >= max_attempts:
            raise issue
        time.sleep(backoff_seconds * attempts)


def count_skips_by_reason(skips: list[SymbolSkip] | tuple[SymbolSkip, ...]) -> dict[str, int]:
    counts = Counter(skip.reason_code for skip in skips)
    return {key: counts[key] for key in sorted(counts)}


def summarize_skips(skips: list[SymbolSkip] | tuple[SymbolSkip, ...]) -> str:
    if not skips:
        return "none"
    counts = count_skips_by_reason(skips)
    return ", ".join(f"{reason}={count}" for reason, count in counts.items())


def representative_skip_details(skips: list[SymbolSkip] | tuple[SymbolSkip, ...], limit: int = 3) -> list[str]:
    lines: list[str] = []
    seen: set[tuple[str, str]] = set()
    for skip in skips:
        key = (skip.reason_code, skip.detail)
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"{skip.symbol} [{skip.reason_code} at {skip.stage}]: {skip.detail}")
        if len(lines) >= limit:
            break
    return lines
