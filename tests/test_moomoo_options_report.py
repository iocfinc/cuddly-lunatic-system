from __future__ import annotations

import datetime as dt
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quant_researcher_desk.moomoo_options_report import (  # noqa: E402
    RISK_NOTE,
    build_options_report,
    format_telegram_html,
    nearest_expiry,
    target_expiry,
)


class FakeQuoteClient:
    def __init__(self) -> None:
        self.closed = False

    def get_underlying_snapshot(self, symbol: str) -> dict[str, object]:
        assert symbol == "US.TSM"
        return {"code": symbol, "last_price": 100.0}

    def get_option_expirations(self, symbol: str) -> list[str]:
        return ["2026-04-24", "2026-05-01", "2026-05-08"]

    def get_option_chain(self, symbol: str, expiry: str) -> list[dict[str, object]]:
        assert expiry == "2026-05-01"
        return [
            {"code": "US.TSM260501C100000", "option_type": "CALL", "strike_price": 100, "strike_time": expiry},
            {"code": "US.TSM260501C105000", "option_type": "CALL", "strike_price": 105, "strike_time": expiry},
            {"code": "US.TSM260501C95000", "option_type": "CALL", "strike_price": 95, "strike_time": expiry},
            {"code": "US.TSM260501P100000", "option_type": "PUT", "strike_price": 100, "strike_time": expiry},
            {"code": "US.TSM260501P105000", "option_type": "PUT", "strike_price": 105, "strike_time": expiry},
            {"code": "US.TSM260501P95000", "option_type": "PUT", "strike_price": 95, "strike_time": expiry},
        ]

    def get_market_snapshots(self, codes: list[str]) -> list[dict[str, object]]:
        snapshots = {
            "US.TSM260501C100000": {"code": "US.TSM260501C100000", "last_price": 5.0, "implied_volatility": 0.41, "delta": 0.52, "open_interest": 40, "volume": 100},
            "US.TSM260501C105000": {"code": "US.TSM260501C105000", "last_price": 2.5, "implied_volatility": 0.44, "delta": 0.35, "open_interest": 80, "volume": 100},
            "US.TSM260501C95000": {"code": "US.TSM260501C95000", "last_price": 8.0, "implied_volatility": 0.39, "delta": 0.68, "open_interest": 10, "volume": 20},
            "US.TSM260501P100000": {"code": "US.TSM260501P100000", "last_price": 4.5, "implied_volatility": 0.42, "delta": -0.48, "open_interest": 30, "volume": 70},
            "US.TSM260501P105000": {"code": "US.TSM260501P105000", "last_price": 7.5, "implied_volatility": 0.45, "delta": -0.65, "open_interest": 30, "volume": 70},
            "US.TSM260501P95000": {"code": "US.TSM260501P95000", "last_price": 2.0, "implied_volatility": 0.38, "delta": -0.31, "open_interest": 100, "volume": 10},
        }
        return [snapshots[code] for code in codes]

    def close(self) -> None:
        self.closed = True


def test_nearest_expiry_selects_future_date() -> None:
    assert nearest_expiry(["2026-04-24", "2026-05-08", "2026-05-01"], today=dt.date(2026, 4, 28)) == "2026-05-01"


def test_target_expiry_selects_proactive_window_and_skips_same_day() -> None:
    assert (
        target_expiry(
            ["2026-04-29", "2026-05-01", "2026-05-06", "2026-05-15"],
            today=dt.date(2026, 4, 29),
            minimum_days_out=5,
            target_days_out=7,
        )
        == "2026-05-06"
    )


def test_build_options_report_ranks_by_volume_open_interest_then_strike_distance() -> None:
    report = build_options_report(
        FakeQuoteClient(),
        "US.TSM",
        rows=2,
        now=dt.datetime(2026, 4, 28, 9, 30, tzinfo=dt.timezone.utc),
    )

    assert report.underlying_price == 100.0
    assert report.expiry == "2026-05-01"
    assert report.scanned_contract_count == 6
    assert [option.strike for option in report.calls] == [105.0, 100.0]
    assert [option.strike for option in report.puts] == [100.0, 105.0]


def test_telegram_html_escapes_text_and_includes_required_fields() -> None:
    report = build_options_report(
        FakeQuoteClient(),
        "US.TSM",
        rows=1,
        now=dt.datetime(2026, 4, 28, 9, 30, tzinfo=dt.timezone.utc),
    )
    message = format_telegram_html(report)

    assert "<b>Quant Researcher Desk - US.TSM Options</b>" in message
    assert "Generated: <code>2026-04-28 09:30:00 UTC</code>" in message
    assert "Underlying latest: <code>100.00</code>" in message
    assert "Selected expiry: <code>2026-05-01</code>" in message
    assert "Scanned contracts: <code>6</code>" in message
    assert "Strike | Last | IV | Delta | OI | Vol" in message
    assert "105.00 | 2.50 | 0.44 | 0.350 | 80 | 100" in message
    assert RISK_NOTE in message
