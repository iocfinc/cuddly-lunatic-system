from __future__ import annotations

import datetime as dt
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quant_researcher_desk.catalyst_options_screen import (  # noqa: E402
    CatalystCandidate,
    UNVERIFIED_TIMING_NOTE,
    build_catalyst_options_screen,
    catalyst_report_sections,
    format_catalyst_telegram_html,
)
from quant_researcher_desk.options_research import EarningsContext  # noqa: E402


class FakeCatalystClient:
    def get_underlying_snapshot(self, symbol: str) -> dict[str, object]:
        return {"code": symbol, "last_price": 100.0}

    def get_option_expirations(self, symbol: str) -> list[str]:
        return ["2026-04-29", "2026-05-01", "2026-05-06", "2026-05-08"]

    def get_option_chain(self, symbol: str, expiry: str) -> list[dict[str, object]]:
        return [
            {"code": f"{symbol}C105", "option_type": "CALL", "strike_price": 105.0, "strike_time": expiry},
            {"code": f"{symbol}P95", "option_type": "PUT", "strike_price": 95.0, "strike_time": expiry},
        ]

    def get_market_snapshots(self, codes: list[str]) -> list[dict[str, object]]:
        rows = []
        for code in codes:
            if code.endswith("C105"):
                rows.append({"code": code, "last_price": 2.2, "implied_volatility": 0.55, "delta": 0.35, "open_interest": 1200, "volume": 800})
            else:
                rows.append({"code": code, "last_price": 1.9, "implied_volatility": 0.58, "delta": -0.30, "open_interest": 900, "volume": 500})
        return rows

    def get_daily_bars(self, symbol: str, count: int = 250) -> list[dict[str, object]]:
        del symbol
        return [
            {"time_key": (dt.date(2025, 1, 1) + dt.timedelta(days=index)).isoformat(), "close": 100.0 + index}
            for index in range(count)
        ]

    def get_earnings_context(self, symbol: str) -> EarningsContext:
        del symbol
        return EarningsContext(
            next_date="2026-05-12",
            phase="post-window",
            summary="Fixture context: mapped event sits outside the intended holding window.",
            risk_level="low",
            within_holding_window=False,
            source="fixture",
        )

    def close(self) -> None:
        return None


class MixedTrendCatalystClient(FakeCatalystClient):
    def get_daily_bars(self, symbol: str, count: int = 250) -> list[dict[str, object]]:
        del symbol
        closes = [100.0] * (count - 60) + [95.0] * 20 + [105.0] * 20 + [98.0] * 20
        return [
            {"time_key": (dt.date(2025, 1, 1) + dt.timedelta(days=index)).isoformat(), "close": close}
            for index, close in enumerate(closes)
        ]


def test_build_catalyst_options_screen_runs_stock_first_and_keeps_only_aligned_side() -> None:
    candidates = (
        CatalystCandidate("US.TEST", "Test Co", "Mapped earnings watch", UNVERIFIED_TIMING_NOTE, "Use readable delta."),
    )

    report = build_catalyst_options_screen(
        FakeCatalystClient(),
        candidates,
        now=dt.datetime(2026, 4, 29, 9, 30, tzinfo=dt.timezone.utc),
    )

    assert len(report.ideas) == 1
    assert report.ideas[0].symbol == "US.TEST"
    assert report.ideas[0].side == "Call"
    assert report.ideas[0].option.strike == 105.0
    assert report.ideas[0].expiry == "2026-05-06"
    assert report.ideas[0].review_level == "Priority Review"
    assert report.ideas[0].stock_direction == "bullish"
    assert report.assessments[0].timing.startswith("2026-05-12")
    assert report.minimum_days_out == 5
    assert report.target_days_out == 7
    assert not report.skipped


def test_catalyst_report_sections_include_learning_corner_and_ranked_table() -> None:
    candidates = (
        CatalystCandidate("US.TEST", "Test Co", "Mapped earnings watch", UNVERIFIED_TIMING_NOTE, "Use readable delta."),
    )
    report = build_catalyst_options_screen(
        FakeCatalystClient(),
        candidates,
        now=dt.datetime(2026, 4, 29, 9, 30, tzinfo=dt.timezone.utc),
    )

    sections = {str(section["title"]): section for section in catalyst_report_sections(report)}

    assert "Ranked Option Ideas" in sections
    assert "Learning Corner" in sections
    assert "stock has a clean bullish or bearish regime" in str(sections["Learning Corner"]["content"])
    assert "conditional watch bucket" in str(sections["Learning Corner"]["content"])
    assert sections["Ranked Option Ideas"]["table"][0]["symbol"] == "TEST"  # type: ignore[index]
    assert sections["Catalyst Watchlist Status"]["table"][0]["review_level"] == "Priority Review"  # type: ignore[index]


def test_format_catalyst_telegram_html_is_one_compact_message() -> None:
    candidates = (
        CatalystCandidate("US.TEST", "Test Co", "Mapped earnings watch", UNVERIFIED_TIMING_NOTE, "Use readable delta."),
    )
    report = build_catalyst_options_screen(
        FakeCatalystClient(),
        candidates,
        now=dt.datetime(2026, 4, 29, 9, 30, tzinfo=dt.timezone.utc),
    )

    message = format_catalyst_telegram_html(report)

    assert "<b>📊 Catalyst Options Screen</b>" in message
    assert "<b>TEST</b> Priority Review | Call" in message
    assert "Expiry lens" in message
    assert "PDF attached" in message


def test_build_catalyst_options_screen_skips_mixed_regimes_instead_of_forcing_countertrend() -> None:
    candidates = (
        CatalystCandidate("US.TEST", "Test Co", "Mapped earnings watch", UNVERIFIED_TIMING_NOTE, "Use readable delta."),
    )

    report = build_catalyst_options_screen(
        MixedTrendCatalystClient(),
        candidates,
        now=dt.datetime(2026, 4, 29, 9, 30, tzinfo=dt.timezone.utc),
    )

    assert not report.ideas
    assert report.assessments[0].review_level == "Pass"
    assert report.assessments[0].top_option == "Skip mixed or unresolved stock regime"
    assert "stock-first gate blocked" in report.skipped[0]


def test_default_candidates_use_unverified_timing_note_instead_of_historical_labels() -> None:
    report = build_catalyst_options_screen(
        FakeCatalystClient(),
        now=dt.datetime(2026, 4, 29, 9, 30, tzinfo=dt.timezone.utc),
    )

    stale_tokens = {"Apr 29", "Apr 30", "May 1", "This week"}
    assert all(candidate.timing == UNVERIFIED_TIMING_NOTE for candidate in report.candidates)
    assert stale_tokens.isdisjoint({candidate.timing for candidate in report.candidates})
