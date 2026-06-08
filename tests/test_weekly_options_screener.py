from __future__ import annotations

import datetime as dt
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quant_researcher_desk.moomoo_options_report import OptionsReportError  # noqa: E402
from quant_researcher_desk.options_research import EarningsContext, monte_carlo_option_price  # noqa: E402
from quant_researcher_desk.weekly_options_screener import (  # noqa: E402
    ScreenedOption,
    FixtureWeeklyScreenProvider,
    WeeklyReviewerConfig,
    WeeklyScreenRequest,
    _review_shortlisted_option,
    build_weekly_options_screen,
    discover_universe,
    result_payload,
    shortlist_rows,
    write_shortlist_html,
    write_shortlist_pdf,
)


def _gate_result_by_symbol(report, symbol: str):  # type: ignore[no-untyped-def]
    for gate_result in report.gate_results:
        if gate_result.symbol == symbol:
            return gate_result
    raise AssertionError(f"Missing gate result for {symbol}")


class FakeWeeklyQuoteClient:
    def __init__(self) -> None:
        self.option_symbols = {"US.AAPL", "US.MSFT", "US.NVDA"}

    def get_plate_list(self, market: str, plate_type: str = "ALL") -> list[dict[str, object]]:
        assert market == "US"
        assert plate_type == "ALL"
        return [
            {"code": "US.TECH", "plate_name": "US Technology"},
            {"code": "US.MEGA", "plate_name": "US Mega Caps"},
        ]

    def get_plate_constituents(self, plate_code: str) -> list[dict[str, object]]:
        rows = {
            "US.TECH": [
                {"code": "US.NVDA", "stock_name": "NVIDIA"},
                {"code": "US.MSFT", "stock_name": "Microsoft"},
            ],
            "US.MEGA": [
                {"code": "US.AAPL", "stock_name": "Apple"},
                {"code": "US.MSFT", "stock_name": "Microsoft"},
                {"code": "US.NOOPT", "stock_name": "No Options Co"},
            ],
        }
        return list(rows[plate_code])

    def get_underlying_snapshot(self, symbol: str) -> dict[str, object]:
        prices = {"US.AAPL": 195.0, "US.MSFT": 430.0, "US.NVDA": 118.0}
        return {"code": symbol, "last_price": prices[symbol]}

    def get_option_expirations(self, symbol: str) -> list[str]:
        expiries = {
            "US.AAPL": ["2026-05-29", "2026-06-05"],
            "US.MSFT": ["2026-05-30", "2026-06-01"],
            "US.NVDA": ["2026-05-31"],
        }
        if symbol not in expiries:
            return []
        return expiries[symbol]

    def get_option_chain(self, symbol: str, expiry: str) -> list[dict[str, object]]:
        rows = {
            ("US.AAPL", "2026-05-29"): [
                {"code": "US.AAPL260529C195000", "option_type": "CALL", "strike_price": 195.0, "strike_time": expiry},
                {"code": "US.AAPL260529P190000", "option_type": "PUT", "strike_price": 190.0, "strike_time": expiry},
                {"code": "US.AAPL260529C205000", "option_type": "CALL", "strike_price": 205.0, "strike_time": expiry},
                {"code": "US.AAPL260529C200000", "option_type": "CALL", "strike_price": 200.0, "strike_time": expiry},
            ],
            ("US.MSFT", "2026-06-01"): [
                {"code": "US.MSFT260601C430000", "option_type": "CALL", "strike_price": 430.0, "strike_time": expiry},
                {"code": "US.MSFT260601P420000", "option_type": "PUT", "strike_price": 420.0, "strike_time": expiry},
                {"code": "US.MSFT260601P410000", "option_type": "PUT", "strike_price": 410.0, "strike_time": expiry},
            ],
            ("US.NVDA", "2026-05-31"): [
                {"code": "US.NVDA260531C120000", "option_type": "CALL", "strike_price": 120.0, "strike_time": expiry},
                {"code": "US.NVDA260531P115000", "option_type": "PUT", "strike_price": 115.0, "strike_time": expiry},
            ],
        }
        return list(rows.get((symbol, expiry), []))

    def get_market_snapshots(self, codes: list[str]) -> list[dict[str, object]]:
        snapshots = {
            "US.AAPL260529C195000": {"code": "US.AAPL260529C195000", "last_price": 5.2, "implied_volatility": 0.26, "delta": 0.52, "open_interest": 2400, "volume": 1800},
            "US.AAPL260529P190000": {"code": "US.AAPL260529P190000", "last_price": 3.7, "implied_volatility": 0.27, "delta": -0.33, "open_interest": 2000, "volume": 1400},
            "US.AAPL260529C205000": {"code": "US.AAPL260529C205000", "last_price": 2.4, "implied_volatility": 0.24, "delta": 0.31, "open_interest": 1200, "volume": 820},
            "US.AAPL260529C200000": {"code": "US.AAPL260529C200000", "last_price": 3.6, "implied_volatility": 0.25, "delta": 0.42, "open_interest": 1600, "volume": 1100},
            "US.MSFT260601C430000": {"code": "US.MSFT260601C430000", "last_price": 6.0, "implied_volatility": 0.23, "delta": 0.51, "open_interest": 2500, "volume": 1600},
            "US.MSFT260601P420000": {"code": "US.MSFT260601P420000", "last_price": 5.8, "implied_volatility": 0.24, "delta": -0.39, "open_interest": 2100, "volume": 1450},
            "US.MSFT260601P410000": {"code": "US.MSFT260601P410000", "last_price": 3.4, "implied_volatility": 0.22, "delta": -0.29, "open_interest": 1700, "volume": 1200},
            "US.NVDA260531C120000": {"code": "US.NVDA260531C120000", "last_price": 0.0, "implied_volatility": 0.35, "delta": 0.44, "open_interest": 1900, "volume": 1300},
            "US.NVDA260531P115000": {"code": "US.NVDA260531P115000", "last_price": 2.2, "implied_volatility": 0.37, "delta": -0.22, "open_interest": 40, "volume": 35},
        }
        return [snapshots[code] for code in codes]

    def get_daily_bars(self, symbol: str, count: int = 250) -> list[dict[str, object]]:
        start = dt.date(2025, 1, 1)
        histories = {
            "US.AAPL": [100.0 + index * 0.8 for index in range(250)],
            "US.MSFT": [300.0 - index * 0.7 for index in range(250)],
            "US.NVDA": [120.0 + index * 0.15 for index in range(230)] + [160.0 - index * 1.1 for index in range(20)],
            "US.NOOPT": [80.0 + index * 0.4 for index in range(250)],
        }
        closes = histories[symbol][-count:]
        return [
            {"time_key": (start + dt.timedelta(days=index)).isoformat(), "close": close}
            for index, close in enumerate(closes)
        ]

    def close(self) -> None:
        return None


class RateLimitedPlateQuoteClient:
    def __init__(self) -> None:
        self.plate_calls = 0

    def get_plate_list(self, market: str, plate_type: str = "ALL") -> list[dict[str, object]]:
        assert market == "US"
        return [
            {"code": f"US.PLATE{i:02d}", "plate_name": f"Plate {i:02d}"}
            for i in range(12)
        ]

    def get_plate_constituents(self, plate_code: str) -> list[dict[str, object]]:
        self.plate_calls += 1
        if self.plate_calls > 10:
            raise OptionsReportError(
                "OpenD failed to get plate constituents for "
                f"{plate_code}: Get Stock List within a Sector request failed due to high frequency. "
                "Maximum 10 times per 30 seconds."
            )
        return [
            {"code": f"US.{plate_code.split('.')[-1]}A", "stock_name": f"{plate_code} A"},
            {"code": f"US.{plate_code.split('.')[-1]}B", "stock_name": f"{plate_code} B"},
        ]


class LargePlateQuoteClient:
    def __init__(self) -> None:
        self.plate_calls = 0

    def get_plate_list(self, market: str, plate_type: str = "ALL") -> list[dict[str, object]]:
        assert market == "US"
        return [
            {"code": "US.PLATE01", "plate_name": "Plate 01"},
            {"code": "US.PLATE02", "plate_name": "Plate 02"},
            {"code": "US.PLATE03", "plate_name": "Plate 03"},
        ]

    def get_plate_constituents(self, plate_code: str) -> list[dict[str, object]]:
        self.plate_calls += 1
        rows = {
            "US.PLATE01": [
                {"code": "US.AAPL", "stock_name": "Apple"},
                {"code": "US.MSFT", "stock_name": "Microsoft"},
                {"code": "US.NVDA", "stock_name": "NVIDIA"},
            ],
            "US.PLATE02": [
                {"code": "US.AMD", "stock_name": "AMD"},
                {"code": "US.AMZN", "stock_name": "Amazon"},
                {"code": "US.META", "stock_name": "Meta"},
            ],
            "US.PLATE03": [
                {"code": "US.GOOGL", "stock_name": "Alphabet"},
            ],
        }
        return list(rows[plate_code])


class ProviderCollapseQuoteClient:
    def get_plate_list(self, market: str, plate_type: str = "ALL") -> list[dict[str, object]]:
        assert market == "US"
        return [{"code": "US.TECH", "plate_name": "US Technology"}]

    def get_plate_constituents(self, plate_code: str) -> list[dict[str, object]]:
        return [
            {"code": f"US.FAIL{i:02d}", "stock_name": f"Fail {i:02d}"}
            for i in range(12)
        ]

    def get_option_expirations(self, symbol: str) -> list[str]:
        raise OptionsReportError(
            f"OpenD failed to get option expirations for {symbol}: request failed due to high frequency rate limit."
        )


def test_monte_carlo_option_price_is_seeded_and_non_negative() -> None:
    price_one = monte_carlo_option_price(
        option_type="CALL",
        spot=100.0,
        strike=100.0,
        years=7 / 365,
        volatility=0.25,
        risk_free_rate=0.04,
        seed=7,
        iterations=4000,
    )
    price_two = monte_carlo_option_price(
        option_type="CALL",
        spot=100.0,
        strike=100.0,
        years=7 / 365,
        volatility=0.25,
        risk_free_rate=0.04,
        seed=7,
        iterations=4000,
    )

    assert price_one == pytest.approx(price_two, abs=1e-9)
    assert price_one >= 0.0


def test_monte_carlo_option_price_increases_with_volatility_and_time() -> None:
    short_low_vol = monte_carlo_option_price("CALL", 100.0, 100.0, 5 / 365, 0.15, seed=11, iterations=6000)
    short_high_vol = monte_carlo_option_price("CALL", 100.0, 100.0, 5 / 365, 0.35, seed=11, iterations=6000)
    long_high_vol = monte_carlo_option_price("CALL", 100.0, 100.0, 9 / 365, 0.35, seed=11, iterations=6000)

    assert short_high_vol > short_low_vol
    assert long_high_vol > short_high_vol


def test_build_weekly_options_screen_dedupes_universe_and_filters_bad_contracts() -> None:
    report = build_weekly_options_screen(
        FakeWeeklyQuoteClient(),
        WeeklyScreenRequest(
            market="US",
            top_n=4,
            minimum_days_out=5,
            target_days_out=7,
            min_volume=100,
            min_open_interest=100,
            min_abs_delta=0.20,
            max_abs_delta=0.60,
            historical_volatility=0.22,
            max_underlyings=10,
        ),
        now=dt.datetime(2026, 5, 24, 9, 30, tzinfo=dt.timezone.utc),
    )

    assert report.discovery_stats["raw_constituents"] == 5
    assert report.discovery_stats["unique_underlyings"] == 4
    assert report.discovery_stats["with_target_expiry"] == 2
    assert report.discovery_stats["no_expirations"] == 1
    assert "US.NOOPT" in report.skipped_underlyings
    assert {skip.symbol: skip.reason_code for skip in report.skipped_symbols} == {
        "US.NOOPT": "no_expirations",
        "US.NVDA": "mixed_trend_regime",
    }
    nvda_gate = _gate_result_by_symbol(report, "US.NVDA")
    assert any(
        decision.stage == "stock_context" and decision.status == "failed" and decision.reason_code == "mixed_trend_regime"
        for decision in nvda_gate.decisions
    )
    assert len(report.ranked_options) == 4
    assert all(contract.symbol != "US.NVDA" for contract in report.ranked_options)
    assert all(contract.premium > 0 for contract in report.ranked_options)
    assert all(contract.volume >= 100 for contract in report.ranked_options)
    assert all(contract.open_interest >= 100 for contract in report.ranked_options)
    assert all(0.20 <= abs(contract.delta) <= 0.60 for contract in report.ranked_options)
    assert {contract.symbol: contract.side for contract in report.ranked_options[:2]} == {
        "US.AAPL": "CALL",
        "US.MSFT": "PUT",
    }


def test_discover_universe_returns_partial_results_when_plate_queries_hit_opend_rate_limit() -> None:
    client = RateLimitedPlateQuoteClient()

    universe, stats = discover_universe(client, "US", max_underlyings=250)

    assert client.plate_calls == 11
    assert len(universe) == 20
    assert stats["plates"] == 12
    assert stats["raw_constituents"] == 20
    assert stats["unique_underlyings"] == 20
    assert stats["plate_rate_limit_hits"] == 1


def test_discover_universe_stops_querying_new_plates_once_max_underlyings_is_reached() -> None:
    client = LargePlateQuoteClient()

    universe, stats = discover_universe(client, "US", max_underlyings=5)

    assert client.plate_calls == 2
    assert len(universe) == 5
    assert stats["raw_constituents"] == 6
    assert stats["unique_underlyings"] == 6
    assert stats["plate_rate_limit_hits"] == 0


def test_build_weekly_options_screen_prefers_liquid_contracts_when_edges_are_similar() -> None:
    report = build_weekly_options_screen(
        FakeWeeklyQuoteClient(),
        WeeklyScreenRequest(market="US", top_n=2, historical_volatility=0.22),
        now=dt.datetime(2026, 5, 24, 9, 30, tzinfo=dt.timezone.utc),
    )

    assert [contract.symbol for contract in report.ranked_options] == ["US.AAPL", "US.MSFT"]
    assert report.ranked_options[0].exit_quality_score >= 0.85
    assert report.ranked_options[1].exit_quality_score >= 0.85
    assert "exit quality" in report.ranked_options[0].reason.lower()


def test_build_weekly_options_screen_treats_live_expiration_errors_like_empty_expiration_lists() -> None:
    class LiveLikeExpiryErrorClient(FakeWeeklyQuoteClient):
        def get_option_expirations(self, symbol: str) -> list[str]:
            if symbol == "US.NOOPT":
                raise OptionsReportError("No option expirations returned for US.NOOPT.")
            return super().get_option_expirations(symbol)

    report = build_weekly_options_screen(
        LiveLikeExpiryErrorClient(),
        WeeklyScreenRequest(market="US", top_n=3, historical_volatility=0.22),
        now=dt.datetime(2026, 5, 24, 9, 30, tzinfo=dt.timezone.utc),
    )

    assert any(skip.symbol == "US.NOOPT" and skip.reason_code == "no_expirations" for skip in report.skipped_symbols)
    assert len(report.ranked_options) == 3


def test_build_weekly_options_screen_recovers_from_missing_snapshots_and_underlying_gaps() -> None:
    class MissingDataClient(FakeWeeklyQuoteClient):
        def get_daily_bars(self, symbol: str, count: int = 250) -> list[dict[str, object]]:
            if symbol == "US.NVDA":
                start = dt.date(2025, 1, 1)
                closes = [90.0 + index * 0.7 for index in range(count)]
                return [
                    {"time_key": (start + dt.timedelta(days=index)).isoformat(), "close": close}
                    for index, close in enumerate(closes)
                ]
            return super().get_daily_bars(symbol, count=count)

        def get_underlying_snapshot(self, symbol: str) -> dict[str, object]:
            if symbol == "US.AAPL":
                return {"code": symbol, "last_price": None}
            return super().get_underlying_snapshot(symbol)

        def get_market_snapshots(self, codes: list[str]) -> list[dict[str, object]]:
            if any(code.startswith("US.MSFT") for code in codes):
                return []
            rows = super().get_market_snapshots(codes)
            for row in rows:
                if str(row["code"]).startswith("US.NVDA"):
                    row.update({"last_price": 3.4, "open_interest": 2200, "volume": 1600, "delta": 0.41})
            return rows

    report = build_weekly_options_screen(
        MissingDataClient(),
        WeeklyScreenRequest(market="US", top_n=2, historical_volatility=0.22),
        now=dt.datetime(2026, 5, 24, 9, 30, tzinfo=dt.timezone.utc),
    )

    assert any(skip.symbol == "US.AAPL" and skip.reason_code == "missing_underlying_snapshot" for skip in report.skipped_symbols)
    assert any(skip.symbol == "US.MSFT" and skip.reason_code == "missing_contract_snapshot" for skip in report.skipped_symbols)
    assert any(
        decision.stage == "contract_quality" and decision.status == "failed" and decision.reason_code == "missing_contract_snapshot"
        for decision in _gate_result_by_symbol(report, "US.MSFT").decisions
    )
    assert len(report.ranked_options) == 1
    assert {option.symbol for option in report.ranked_options} == {"US.NVDA"}


def test_build_weekly_options_screen_fails_only_when_all_symbols_are_skipped() -> None:
    class EmptyUniverseClient(FakeWeeklyQuoteClient):
        def get_plate_constituents(self, plate_code: str) -> list[dict[str, object]]:
            return [{"code": "US.NOOPT", "stock_name": "No Options Co"}]

        def get_option_expirations(self, symbol: str) -> list[str]:
            return []

    with pytest.raises(OptionsReportError, match=r"No viable weekly options remained after screening.*no_expirations=1"):
        build_weekly_options_screen(
            EmptyUniverseClient(),
            WeeklyScreenRequest(market="US", top_n=2, historical_volatility=0.22),
            now=dt.datetime(2026, 5, 24, 9, 30, tzinfo=dt.timezone.utc),
        )


def test_build_weekly_options_screen_aborts_with_provider_collapse_message() -> None:
    with pytest.raises(OptionsReportError, match=r"OpenD transient provider failures dominated") as excinfo:
        build_weekly_options_screen(
            ProviderCollapseQuoteClient(),
            WeeklyScreenRequest(
                market="US",
                top_n=2,
                historical_volatility=0.22,
                max_underlyings=12,
                analysis_mode="options-first",
            ),
            now=dt.datetime(2026, 5, 24, 9, 30, tzinfo=dt.timezone.utc),
        )

    message = str(excinfo.value)
    assert "provider_rate_limited" in message
    assert "Retry after the provider cooldown window or reduce max_underlyings." in message


def test_shortlist_rows_include_required_screen_columns() -> None:
    report = build_weekly_options_screen(
        FakeWeeklyQuoteClient(),
        WeeklyScreenRequest(market="US", top_n=1, historical_volatility=0.22),
        now=dt.datetime(2026, 5, 24, 9, 30, tzinfo=dt.timezone.utc),
    )

    row = shortlist_rows(report)[0]
    assert row["symbol"] in {"US.AAPL", "US.MSFT"}
    assert set(
        [
            "symbol",
            "side",
            "expiry",
            "strike",
            "premium",
            "delta",
            "iv",
            "volume",
            "open_interest",
            "black_scholes_fair_value",
            "monte_carlo_fair_value",
            "model_edge",
            "model_edge_pct",
            "fair_value_gap_pct",
            "valuation_view",
            "pricing_engine",
            "shadow_compare",
            "trend_regime",
            "stock_direction",
            "stock_review_summary",
            "invalidation",
            "alignment_status",
            "reason",
            "directional_fit_score",
            "exit_quality_score",
            "valuation_context_score",
            "event_risk_score",
            "event_risk",
            "event_risk_detail",
            "review_status",
            "review_flags",
        ]
    ).issubset(row.keys())


def test_build_weekly_options_screen_can_review_shortlist_without_blocking_output() -> None:
    report = build_weekly_options_screen(
        FakeWeeklyQuoteClient(),
        WeeklyScreenRequest(
            market="US",
            top_n=3,
            historical_volatility=0.22,
            pricing_engine="legacy",
            shadow_compare=True,
            review_shortlist=True,
        ),
        now=dt.datetime(2026, 5, 24, 9, 30, tzinfo=dt.timezone.utc),
        reviewer_config=WeeklyReviewerConfig(enabled=True, reviewer_model=None, reviewer_profile=None),
    )

    assert report.review_summary is not None
    assert report.reviewed_shortlist is True
    assert any(option.review_status != "Not Reviewed" for option in report.ranked_options)
    assert any(option.review_flags for option in report.ranked_options)

    payload = result_payload(report)
    assert payload["review_summary"]
    assert payload["reviewed_shortlist"] is True
    assert payload["gate_results"]
    assert payload["gate_summary"]["stage_rows"]
    assert payload["ranked_options"][0]["review_status"] in {"Candidate", "Watch", "Reject", "Needs Human Review"}


def test_gate_trace_marks_missing_daily_bars_at_stock_context_stage() -> None:
    class MissingDailyBarsClient(FakeWeeklyQuoteClient):
        def get_daily_bars(self, symbol: str, count: int = 250) -> list[dict[str, object]]:
            if symbol == "US.AAPL":
                return []
            return super().get_daily_bars(symbol, count=count)

    report = build_weekly_options_screen(
        MissingDailyBarsClient(),
        WeeklyScreenRequest(market="US", top_n=2, historical_volatility=0.22),
        now=dt.datetime(2026, 5, 24, 9, 30, tzinfo=dt.timezone.utc),
    )

    apple_gate = _gate_result_by_symbol(report, "US.AAPL")
    assert any(
        decision.stage == "stock_context" and decision.status == "failed" and decision.reason_code == "missing_daily_bars"
        for decision in apple_gate.decisions
    )


def test_gate_trace_marks_missing_weekly_expiry_at_weekly_expiry_stage() -> None:
    report = build_weekly_options_screen(
        FakeWeeklyQuoteClient(),
        WeeklyScreenRequest(market="US", top_n=3, historical_volatility=0.22),
        now=dt.datetime(2026, 5, 24, 9, 30, tzinfo=dt.timezone.utc),
    )

    noopt_gate = _gate_result_by_symbol(report, "US.NOOPT")
    assert any(
        decision.stage == "weekly_expiry" and decision.status == "failed" and decision.reason_code == "no_expirations"
        for decision in noopt_gate.decisions
    )


def test_gate_trace_marks_contract_quality_failure_when_no_contract_survives_filters() -> None:
    class ContractQualityFailureClient(FakeWeeklyQuoteClient):
        def get_daily_bars(self, symbol: str, count: int = 250) -> list[dict[str, object]]:
            if symbol == "US.NVDA":
                start = dt.date(2025, 1, 1)
                closes = [90.0 + index * 0.6 for index in range(count)]
                return [
                    {"time_key": (start + dt.timedelta(days=index)).isoformat(), "close": close}
                    for index, close in enumerate(closes)
                ]
            return super().get_daily_bars(symbol, count=count)

    report = build_weekly_options_screen(
        ContractQualityFailureClient(),
        WeeklyScreenRequest(market="US", top_n=3, historical_volatility=0.22),
        now=dt.datetime(2026, 5, 24, 9, 30, tzinfo=dt.timezone.utc),
    )

    nvda_gate = _gate_result_by_symbol(report, "US.NVDA")
    assert any(
        decision.stage == "contract_quality" and decision.status == "failed" and decision.reason_code == "no_contract_match"
        for decision in nvda_gate.decisions
    )


def test_gate_trace_marks_shortlisted_symbols_at_shortlist_outcome_stage() -> None:
    report = build_weekly_options_screen(
        FakeWeeklyQuoteClient(),
        WeeklyScreenRequest(market="US", top_n=2, historical_volatility=0.22),
        now=dt.datetime(2026, 5, 24, 9, 30, tzinfo=dt.timezone.utc),
    )

    first_symbol = report.ranked_options[0].symbol
    shortlisted_gate = _gate_result_by_symbol(report, first_symbol)
    assert any(
        decision.stage == "shortlist_outcome" and decision.status == "passed" and decision.reason_code == "shortlisted"
        for decision in shortlisted_gate.decisions
    )
    assert all(stage_row.stage for stage_row in report.gate_summary.stage_rows)


def test_screened_option_sort_key_penalizes_illiquid_contracts() -> None:
    liquid = ScreenedOption(
        symbol="US.AAPL",
        company="Apple",
        side="CALL",
        option_code="US.AAPL260529C195000",
        expiry="2026-05-29",
        days_to_expiry=5,
        strike=195.0,
        premium=5.2,
        delta=0.52,
        implied_volatility=0.26,
        volume=1800,
        open_interest=2400,
        underlying_price=195.0,
        black_scholes_fair_value=5.6,
        monte_carlo_fair_value=5.5,
        black_scholes_edge=0.4,
        monte_carlo_edge=0.3,
        model_edge_pct=0.0769,
        fair_value_gap_pct=0.0769,
        valuation_view="Cheap",
        pricing_engine="legacy",
        shadow_compare=False,
        quantlib_vs_legacy_diff=None,
        liquidity_score=1.0,
        expiry_fit_score=0.95,
        iv_hv_adjustment=0.9,
        directional_fit_score=0.92,
        exit_quality_score=0.96,
        valuation_context_score=0.74,
        event_risk_score=0.50,
        event_risk="unknown",
        event_risk_detail="Event timing is unknown, so the lane stays open but carries an explicit caution until catalyst context is verified.",
        event_within_holding_window=None,
        composite_score=0.95,
        reason="Liquidity and pricing align.",
        review_status="Candidate",
        review_flags=(),
        review_notes="Liquidity and model confidence are both strong.",
    )
    illiquid = ScreenedOption(
        **{**liquid.__dict__, "symbol": "US.NVDA", "volume": 30, "open_interest": 40, "liquidity_score": 0.05, "composite_score": 0.18}
    )

    assert liquid.composite_score > illiquid.composite_score


def test_write_shortlist_html_renders_explainer_sections_and_theme_toggle(tmp_path: pathlib.Path) -> None:
    report = build_weekly_options_screen(
        FakeWeeklyQuoteClient(),
        WeeklyScreenRequest(market="US", top_n=3, historical_volatility=0.22, review_shortlist=True),
        now=dt.datetime(2026, 5, 24, 9, 30, tzinfo=dt.timezone.utc),
        reviewer_config=WeeklyReviewerConfig(enabled=True, reviewer_model=None, reviewer_profile=None),
    )

    html_path = write_shortlist_html(tmp_path / "weekly-shortlist.html", report)
    html = html_path.read_text(encoding="utf-8")

    assert "What This Run Is" in html
    assert "How Universe Discovery Works" in html
    assert "Why Some Names Were Skipped" in html
    assert "How Contracts Are Filtered" in html
    assert "How Scoring Works" in html
    assert "Gate Trace" in html
    assert "Ranked Weekly Shortlist" in html
    assert "Shortlist Reviewer" in html
    assert "How To Read The Output Safely" in html
    assert "theme-toggle" in html
    assert "--accent-purple" in html
    assert "--accent-chartreuse" in html
    assert "data-theme" in html
    assert "Calls in shortlist" in html
    assert "US.NOOPT [no_expirations at expirations]" in html


def test_result_payload_includes_structured_skip_rows_and_run_summary() -> None:
    report = build_weekly_options_screen(
        FakeWeeklyQuoteClient(),
        WeeklyScreenRequest(market="US", top_n=3, historical_volatility=0.22),
        now=dt.datetime(2026, 5, 24, 9, 30, tzinfo=dt.timezone.utc),
    )

    payload = result_payload(report)

    assert payload["run_summary"]["attempted_symbols"] == 4
    assert payload["run_summary"]["successful_symbol_count"] == 2
    assert payload["run_summary"]["skipped_by_reason"]["no_expirations"] == 1
    assert payload["run_summary"]["skipped_by_reason"]["mixed_trend_regime"] == 1
    assert payload["skipped_symbols"][0]["reason_code"] in {"mixed_trend_regime", "no_expirations"}


def test_write_shortlist_pdf_creates_pdf_and_html_companion(tmp_path: pathlib.Path) -> None:
    report = build_weekly_options_screen(
        FakeWeeklyQuoteClient(),
        WeeklyScreenRequest(market="US", top_n=2, historical_volatility=0.22),
        now=dt.datetime(2026, 5, 24, 9, 30, tzinfo=dt.timezone.utc),
    )

    pdf_path = write_shortlist_pdf(tmp_path / "weekly-shortlist.pdf", report)

    assert pdf_path.exists()
    assert pdf_path.suffix == ".pdf"
    assert (tmp_path / "weekly-shortlist.html").exists()


def test_fixture_provider_supports_current_date_top_10_under_strict_filters() -> None:
    report = build_weekly_options_screen(
        FixtureWeeklyScreenProvider(anchor_date=dt.date(2026, 5, 26)),
        WeeklyScreenRequest(market="US", top_n=10, historical_volatility=0.22),
        now=dt.datetime(2026, 5, 26, 9, 30, tzinfo=dt.timezone.utc),
    )

    assert len(report.ranked_options) == 10
    assert len({contract.symbol for contract in report.ranked_options}) >= 5
    assert all(contract.option_code for contract in report.ranked_options)
    assert all(contract.valuation_view in {"Cheap", "Near Fair", "Rich"} for contract in report.ranked_options)
    assert all(contract.side == "CALL" for contract in report.ranked_options if contract.stock_direction == "bullish")
    assert all(contract.side == "PUT" for contract in report.ranked_options if contract.stock_direction == "bearish")


def test_stock_first_screen_only_emits_calls_for_bullish_and_puts_for_bearish_names() -> None:
    report = build_weekly_options_screen(
        FakeWeeklyQuoteClient(),
        WeeklyScreenRequest(market="US", top_n=4, historical_volatility=0.22, review_shortlist=True),
        now=dt.datetime(2026, 5, 24, 9, 30, tzinfo=dt.timezone.utc),
        reviewer_config=WeeklyReviewerConfig(enabled=False),
    )

    assert {option.symbol for option in report.ranked_options} == {"US.AAPL", "US.MSFT"}
    assert all(option.side == "CALL" for option in report.ranked_options if option.symbol == "US.AAPL")
    assert all(option.side == "PUT" for option in report.ranked_options if option.symbol == "US.MSFT")
    assert all(option.alignment_status == "Aligned" for option in report.ranked_options)


def test_stock_first_screen_drops_no_trade_stock_reviews(monkeypatch) -> None:
    def fake_stock_review(*args, **kwargs):  # type: ignore[no-untyped-def]
        symbol = args[0].symbol
        if symbol == "US.AAPL":
            return {
                "direction": "no_trade",
                "trend_regime": "bullish",
                "thesis_summary": "Trend is intact but catalyst risk is unresolved.",
                "invalidation": "Break below the 20 day moving average.",
                "catalyst_view": "Event timing unclear.",
                "review_confidence": "medium",
                "countertrend_risk": "high",
            }
        return {
            "direction": "bearish",
            "trend_regime": "bearish",
            "thesis_summary": "Trend remains below all key moving averages.",
            "invalidation": "Close back above the 20 day moving average.",
            "catalyst_view": "No near-term bullish catalyst.",
            "review_confidence": "high",
            "countertrend_risk": "low",
        }

    monkeypatch.setattr("quant_researcher_desk.weekly_options_screener.review_stock_candidate", fake_stock_review)

    report = build_weekly_options_screen(
        FakeWeeklyQuoteClient(),
        WeeklyScreenRequest(market="US", top_n=4, historical_volatility=0.22),
        now=dt.datetime(2026, 5, 24, 9, 30, tzinfo=dt.timezone.utc),
    )

    assert all(option.symbol == "US.MSFT" for option in report.ranked_options)
    assert any(skip.symbol == "US.AAPL" and skip.reason_code == "stock_review_no_trade" for skip in report.skipped_symbols)


def test_countertrend_alignment_is_a_hard_reject() -> None:
    countertrend = ScreenedOption(
        symbol="US.AAPL",
        company="Apple",
        side="PUT",
        option_code="US.AAPL260529P190000",
        expiry="2026-05-29",
        days_to_expiry=5,
        strike=190.0,
        premium=3.7,
        delta=-0.33,
        implied_volatility=0.27,
        volume=1400,
        open_interest=2000,
        underlying_price=195.0,
        black_scholes_fair_value=4.0,
        monte_carlo_fair_value=3.9,
        black_scholes_edge=0.3,
        monte_carlo_edge=0.2,
        model_edge_pct=0.0675,
        fair_value_gap_pct=0.0675,
        valuation_view="Cheap",
        liquidity_score=0.88,
        expiry_fit_score=0.95,
        iv_hv_adjustment=0.9,
        directional_fit_score=0.90,
        exit_quality_score=0.82,
        valuation_context_score=0.70,
        event_risk_score=0.50,
        event_risk="unknown",
        event_risk_detail="Event timing is unknown, so the lane stays open but carries an explicit caution until catalyst context is verified.",
        event_within_holding_window=None,
        composite_score=0.82,
        reason="Countertrend example.",
        review_status="Not Reviewed",
        review_flags=(),
        review_notes="",
        trend_regime="bullish",
        stock_direction="bullish",
        stock_review_summary="Trend stack is bullish.",
        invalidation="Lose the 20 day moving average.",
        alignment_status="Countertrend",
        catalyst_view="No bearish catalyst.",
        stock_review_confidence="high",
        countertrend_risk="high",
    )

    reviewed = _review_shortlisted_option(countertrend, WeeklyScreenRequest(market="US"))

    assert reviewed.review_status == "Reject"


def test_event_inside_holding_window_is_flagged_and_penalized_not_excluded() -> None:
    class EventAwareClient(FakeWeeklyQuoteClient):
        def get_earnings_context(self, symbol: str) -> EarningsContext:
            if symbol == "US.AAPL":
                return EarningsContext(
                    next_date="2026-05-27",
                    phase="pre-earnings",
                    summary="Event sits inside the intended holding window.",
                    risk_level="high",
                    within_holding_window=True,
                    source="fixture",
                )
            return EarningsContext(
                next_date="2026-06-12",
                phase="post-event drift",
                summary="No mapped event inside the holding window.",
                risk_level="low",
                within_holding_window=False,
                source="fixture",
            )

    report = build_weekly_options_screen(
        EventAwareClient(),
        WeeklyScreenRequest(market="US", top_n=4, historical_volatility=0.22, review_shortlist=True),
        now=dt.datetime(2026, 5, 24, 9, 30, tzinfo=dt.timezone.utc),
        reviewer_config=WeeklyReviewerConfig(enabled=False),
    )

    aapl = next(option for option in report.ranked_options if option.symbol == "US.AAPL")
    msft = next(option for option in report.ranked_options if option.symbol == "US.MSFT")

    assert aapl.event_risk == "high"
    assert aapl.event_within_holding_window is True
    assert aapl.composite_score < msft.composite_score
    assert "event_inside_holding_window" in aapl.review_flags


def test_missing_event_provider_yields_unknown_risk_caution_behavior() -> None:
    report = build_weekly_options_screen(
        FakeWeeklyQuoteClient(),
        WeeklyScreenRequest(market="US", top_n=2, historical_volatility=0.22, review_shortlist=True),
        now=dt.datetime(2026, 5, 24, 9, 30, tzinfo=dt.timezone.utc),
        reviewer_config=WeeklyReviewerConfig(enabled=False),
    )

    option = report.ranked_options[0]

    assert option.event_risk == "unknown"
    assert option.event_within_holding_window is None
    assert "unknown" in option.event_risk_detail.lower()
    assert "event_risk_unknown" in option.review_flags


def test_result_payload_includes_stock_first_request_fields() -> None:
    report = build_weekly_options_screen(
        FakeWeeklyQuoteClient(),
        WeeklyScreenRequest(market="US", top_n=2, historical_volatility=0.22),
        now=dt.datetime(2026, 5, 24, 9, 30, tzinfo=dt.timezone.utc),
    )

    payload = result_payload(report)

    assert payload["request"]["analysis_mode"] == "stock-first"
    assert payload["request"]["stock_review"] is True
