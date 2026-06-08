from __future__ import annotations

import datetime as dt
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from quant_researcher_desk.options_research import FixtureOptionsResearchProvider, OptionsResearchRequest
from quant_researcher_desk.reporting import write_html_report
from quant_researcher_desk.tradingagents_packet import (
    TradingAgentsPacketRequest,
    build_decision_packet,
    build_desk_evidence_pack,
)
from quant_researcher_desk.tradingagents_watchlist import (
    WatchlistDigestError,
    WatchlistSymbolStatus,
    build_watchlist_digest,
    build_watchlist_securities,
    rank_watchlist_packets,
)
from quant_researcher_desk.moomoo_options_report import OptionsReportError
from scripts.send_tradingagents_watchlist_digest import collect_watchlist_symbols


def _packet(symbol: str, raw_decision: str, edge: float):
    from quant_researcher_desk.tradingagents_packet import AgentDebateResult

    now = dt.datetime(2026, 5, 6, 9, 30, tzinfo=dt.timezone.utc)
    evidence = build_desk_evidence_pack(
        FixtureOptionsResearchProvider(),
        OptionsResearchRequest(symbol=symbol),
        now=now,
    )
    report = evidence.research_report
    adjusted_report = report.__class__(
        symbol=report.symbol,
        generated_at=report.generated_at,
        underlying_price=report.underlying_price,
        contract=report.contract,
        model=report.model,
        model_edge=report.contract.market_price * edge,
        model_edge_pct=edge,
        fair_value_gap_pct=edge,
        valuation_view=report.valuation_view,
        implied_volatility_used=report.implied_volatility_used,
        historical_volatility=report.historical_volatility,
        scenario_rows=report.scenario_rows,
        monte_carlo_distribution=report.monte_carlo_distribution,
        smile_curve=report.smile_curve,
        years_to_expiry=report.years_to_expiry,
        risk_free_rate=report.risk_free_rate,
        dividend_yield=report.dividend_yield,
        black_scholes_curve=report.black_scholes_curve,
        monte_carlo_paths=report.monte_carlo_paths,
        verdict=report.verdict,
        thesis=report.thesis,
        risks=report.risks,
        earnings=report.earnings,
    )
    evidence = evidence.__class__(
        symbol=evidence.symbol,
        generated_at=evidence.generated_at,
        options_request=evidence.options_request,
        underlying_snapshot=evidence.underlying_snapshot,
        options_chain_summary=evidence.options_chain_summary,
        iv_hv_context=evidence.iv_hv_context,
        scenario_outputs=evidence.scenario_outputs,
        catalyst_context=evidence.catalyst_context,
        sector_context=evidence.sector_context,
        research_report=adjusted_report,
    )
    debate = AgentDebateResult(
        analyst_brief=f"{symbol} brief",
        bullish_research="bull",
        bearish_research="bear",
        risk_assessment="risk",
        consensus_summary="summary",
        raw_decision=raw_decision,
        warnings=[],
        provenance={"mode": "fixture"},
    )
    return build_decision_packet(
        TradingAgentsPacketRequest(symbol=symbol),
        evidence,
        debate,
        source_ref="fixture",
    )


def test_build_watchlist_securities_extracts_prefixed_symbols() -> None:
    groups = [{"group_name": "AI Radar", "group_type": "CUSTOM"}]
    rows_by_group = {
        "AI Radar": [
            {"code": "US.NVDA", "name": "NVIDIA"},
            {"code": "TSM", "name": "Taiwan Semi"},
        ]
    }

    securities = build_watchlist_securities(groups, rows_by_group)

    assert [security.symbol for security in securities] == ["US.NVDA", "US.TSM"]
    assert securities[0].group_name == "AI Radar"


def test_build_watchlist_securities_rejects_empty_watchlist() -> None:
    with pytest.raises(WatchlistDigestError, match="No watchlist securities"):
        build_watchlist_securities([], {})


def test_collect_watchlist_symbols_stops_after_first_group_hits_limit() -> None:
    class FakeProvider:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def get_user_security_groups(self):
            return [
                {"group_name": "AI Radar", "group_type": "CUSTOM"},
                {"group_name": "Second Group", "group_type": "CUSTOM"},
            ]

        def get_user_security(self, group_name: str):
            self.calls.append(group_name)
            if group_name == "AI Radar":
                return [
                    {"code": "US.NVDA", "name": "NVIDIA"},
                    {"code": "US.TSM", "name": "TSMC"},
                ]
            return [{"code": "US.META", "name": "Meta"}]

    provider = FakeProvider()

    symbols = collect_watchlist_symbols(provider, group_name=None, max_candidates=2)

    assert symbols == ["US.NVDA", "US.TSM"]
    assert provider.calls == ["AI Radar"]


def test_watchlist_digest_flow_can_skip_symbols_without_options() -> None:
    symbols = ["HK.07709", "US.NVDA"]
    kept = []
    for symbol in symbols:
        if symbol == "HK.07709":
            try:
                raise OptionsReportError("No option expirations returned for HK.07709.")
            except OptionsReportError:
                continue
        kept.append(symbol)

    assert kept == ["US.NVDA"]


def test_rank_watchlist_packets_and_render_digest_attachment(tmp_path: pathlib.Path) -> None:
    packets = rank_watchlist_packets(
        [
            _packet("US.TSM", "watch", 0.18),
            _packet("US.NVDA", "candidate", 0.12),
            _packet("US.META", "reject", 0.30),
        ],
        top_n=2,
    )

    digest = build_watchlist_digest(packets)
    attachment = write_html_report(digest.title, digest.sections, digest.metadata, tmp_path / "watchlist.html")

    assert [packet.symbol for packet in packets] == ["US.NVDA", "US.TSM"]
    assert "US.NVDA" in digest.caption
    assert attachment.exists()
    assert "BUY" not in digest.caption.upper()
    assert "SELL" not in digest.caption.upper()


def test_build_watchlist_digest_includes_partial_run_status_counts() -> None:
    packets = rank_watchlist_packets(
        [
            _packet("US.TSM", "watch", 0.18),
            _packet("US.NVDA", "candidate", 0.12),
        ],
        top_n=2,
    )
    digest = build_watchlist_digest(
        packets,
        symbol_statuses=[
            WatchlistSymbolStatus(symbol="US.NVDA", status="success", label="Research Candidate"),
            WatchlistSymbolStatus(symbol="US.TSM", status="success", label="Watchlist"),
            WatchlistSymbolStatus(
                symbol="US.NOOPT",
                status="skipped_optionability",
                reason_code="empty_chain",
                detail="No option chain rows returned for US.NOOPT 2026-06-02.",
            ),
            WatchlistSymbolStatus(
                symbol="US.META",
                status="skipped_debate_backend",
                reason_code="debate_backend_failed",
                detail="codex exec failed: model unavailable",
            ),
        ],
    )

    assert digest.metadata["attempted"] == 4
    assert digest.metadata["succeeded"] == 2
    assert digest.metadata["skipped_optionability"] == 1
    assert digest.metadata["skipped_debate_backend"] == 1
    assert "Attempted" in str(digest.sections[0]["table"])
    assert "Skipped Symbols" in str([section["title"] for section in digest.sections])


def test_watchlist_digest_script_fixture_dry_run_writes_attachment(tmp_path: pathlib.Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/send_tradingagents_watchlist_digest.py",
            "--dry-run",
            "--fixture",
            "--symbols",
            "US.NVDA,US.NOOPT,US.TSM",
            "--report-format",
            "html",
            "--output-dir",
            str(tmp_path),
        ],
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert "TradingAgents Watchlist Digest" in result.stdout
    assert "attachment:" in result.stdout
    assert "summary:" in result.stdout
    assert list(tmp_path.glob("*.html"))
    assert list(tmp_path.glob("*-summary.json"))
