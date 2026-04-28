from __future__ import annotations

import datetime as dt
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quant_researcher_desk.catalyst_options_screen import (  # noqa: E402
    CatalystCandidate,
    build_catalyst_options_screen,
    catalyst_report_sections,
    format_catalyst_telegram_html,
)


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

    def close(self) -> None:
        return None


def test_build_catalyst_options_screen_ranks_call_and_put_candidates() -> None:
    candidates = (
        CatalystCandidate("US.TEST", "Test Co", "Earnings tomorrow", "Apr 30", "Use readable delta."),
    )

    report = build_catalyst_options_screen(
        FakeCatalystClient(),
        candidates,
        now=dt.datetime(2026, 4, 29, 9, 30, tzinfo=dt.timezone.utc),
    )

    assert len(report.ideas) == 2
    assert report.ideas[0].symbol == "US.TEST"
    assert report.ideas[0].side == "Call"
    assert report.ideas[0].option.strike == 105.0
    assert report.ideas[0].expiry == "2026-05-06"
    assert report.minimum_days_out == 5
    assert report.target_days_out == 7
    assert not report.skipped


def test_catalyst_report_sections_include_learning_corner_and_ranked_table() -> None:
    candidates = (
        CatalystCandidate("US.TEST", "Test Co", "Earnings tomorrow", "Apr 30", "Use readable delta."),
    )
    report = build_catalyst_options_screen(
        FakeCatalystClient(),
        candidates,
        now=dt.datetime(2026, 4, 29, 9, 30, tzinfo=dt.timezone.utc),
    )

    sections = {str(section["title"]): section for section in catalyst_report_sections(report)}

    assert "Ranked Option Ideas" in sections
    assert "Learning Corner" in sections
    assert "event-options screening" in str(sections["Learning Corner"]["content"])
    assert "same-day expiry" in str(sections["Learning Corner"]["content"])
    assert sections["Ranked Option Ideas"]["table"][0]["symbol"] == "TEST"  # type: ignore[index]


def test_format_catalyst_telegram_html_is_one_compact_message() -> None:
    candidates = (
        CatalystCandidate("US.TEST", "Test Co", "Earnings tomorrow", "Apr 30", "Use readable delta."),
    )
    report = build_catalyst_options_screen(
        FakeCatalystClient(),
        candidates,
        now=dt.datetime(2026, 4, 29, 9, 30, tzinfo=dt.timezone.utc),
    )

    message = format_catalyst_telegram_html(report)

    assert "<b>📊 Catalyst Options Screen</b>" in message
    assert "<b>TEST</b> Call" in message
    assert "Expiry lens" in message
    assert "PDF attached" in message
