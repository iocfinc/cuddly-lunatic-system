from __future__ import annotations

import datetime as dt
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quant_researcher_desk.options_research import FixtureOptionsResearchProvider, OptionsResearchRequest
from quant_researcher_desk.tradingagents_packet import (
    TradingAgentsConfig,
    TradingAgentsIntegrationError,
    TradingAgentsPacketRequest,
    build_decision_packet,
    build_desk_evidence_pack,
    decision_packet_sections,
    format_decision_packet_telegram_html,
    load_tradingagents_config,
    run_tradingagents_debate,
)


def test_load_tradingagents_config_defaults_to_repo_local_disabled_state(tmp_path: pathlib.Path) -> None:
    env = {
        "TRADINGAGENTS_RESULTS_DIR": str(tmp_path / "results"),
        "TRADINGAGENTS_CACHE_DIR": str(tmp_path / "cache"),
        "TRADINGAGENTS_MEMORY_DIR": str(tmp_path / "memory"),
    }

    config = load_tradingagents_config(ROOT, env=env)

    assert config.enabled is False
    assert config.allow_execution is False
    assert config.results_dir == tmp_path / "results"
    assert config.cache_dir == tmp_path / "cache"
    assert config.memory_dir == tmp_path / "memory"


def test_load_tradingagents_config_process_env_overrides_dotenv_values(tmp_path: pathlib.Path) -> None:
    env = {
        "TRADINGAGENTS_ENABLED": "false",
        "TRADINGAGENTS_RESULTS_DIR": str(tmp_path / "dotenv-results"),
    }

    config = load_tradingagents_config(
        ROOT,
        env=env,
        runtime_env={
            "TRADINGAGENTS_ENABLED": "true",
            "TRADINGAGENTS_RESULTS_DIR": str(tmp_path / "runtime-results"),
        },
    )

    assert config.enabled is True
    assert config.results_dir == tmp_path / "runtime-results"


def test_run_tradingagents_debate_fixture_builds_research_only_packet() -> None:
    now = dt.datetime(2026, 5, 3, 9, 30, tzinfo=dt.timezone.utc)
    request = OptionsResearchRequest(symbol="US.TEST", option_type="CALL", strike=100, historical_volatility=0.30)
    evidence_pack = build_desk_evidence_pack(FixtureOptionsResearchProvider(), request, now=now)

    debate = run_tradingagents_debate(
        TradingAgentsConfig(
            enabled=False,
            ref="main",
            llm_provider="openai",
            results_dir=ROOT / "data" / "tradingagents" / "results",
            cache_dir=ROOT / "data" / "tradingagents" / "cache",
            memory_dir=ROOT / "data" / "tradingagents" / "memory",
            allow_execution=False,
        ),
        TradingAgentsPacketRequest(symbol="US.TEST"),
        evidence_pack,
        fixture=True,
    )
    packet = build_decision_packet(
        TradingAgentsPacketRequest(symbol="US.TEST"),
        evidence_pack,
        debate,
        source_ref="fixture",
    )
    rendered = format_decision_packet_telegram_html(packet)

    assert evidence_pack.symbol == "US.TEST"
    assert evidence_pack.options_chain_summary["selected_contract"] == "US.TEST260515C100000"
    assert packet.label in {"Research Candidate", "Watchlist", "Reject", "Needs Human Review"}
    assert "BUY" not in rendered.upper()
    assert "SELL" not in rendered.upper()
    assert "EXECUTE" not in rendered.upper()


def test_run_tradingagents_debate_requires_enablement_for_live_path() -> None:
    now = dt.datetime(2026, 5, 3, 9, 30, tzinfo=dt.timezone.utc)
    evidence_pack = build_desk_evidence_pack(
        FixtureOptionsResearchProvider(),
        OptionsResearchRequest(symbol="US.TEST"),
        now=now,
    )

    with pytest.raises(TradingAgentsIntegrationError, match="TRADINGAGENTS_ENABLED=true"):
        run_tradingagents_debate(
            TradingAgentsConfig(
                enabled=False,
                ref="main",
                llm_provider="openai",
                results_dir=ROOT / "data" / "tradingagents" / "results",
                cache_dir=ROOT / "data" / "tradingagents" / "cache",
                memory_dir=ROOT / "data" / "tradingagents" / "memory",
                allow_execution=False,
            ),
            TradingAgentsPacketRequest(symbol="US.TEST"),
            evidence_pack,
            fixture=False,
        )


def test_run_tradingagents_debate_reports_missing_dependency_actionably(monkeypatch: pytest.MonkeyPatch) -> None:
    now = dt.datetime(2026, 5, 3, 9, 30, tzinfo=dt.timezone.utc)
    evidence_pack = build_desk_evidence_pack(
        FixtureOptionsResearchProvider(),
        OptionsResearchRequest(symbol="US.TEST"),
        now=now,
    )

    real_import = __import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):  # type: ignore[no-untyped-def]
        if name.startswith("tradingagents"):
            raise ModuleNotFoundError("No module named 'tradingagents'")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", fake_import)

    with pytest.raises(TradingAgentsIntegrationError, match="dependency is not installed"):
        run_tradingagents_debate(
            TradingAgentsConfig(
                enabled=True,
                ref="main",
                llm_provider="openai",
                results_dir=ROOT / "data" / "tradingagents" / "results",
                cache_dir=ROOT / "data" / "tradingagents" / "cache",
                memory_dir=ROOT / "data" / "tradingagents" / "memory",
                allow_execution=False,
            ),
            TradingAgentsPacketRequest(symbol="US.TEST"),
            evidence_pack,
            fixture=False,
        )


def test_decision_packet_sections_do_not_leak_execution_language() -> None:
    now = dt.datetime(2026, 5, 3, 9, 30, tzinfo=dt.timezone.utc)
    request = OptionsResearchRequest(symbol="US.TEST")
    evidence_pack = build_desk_evidence_pack(FixtureOptionsResearchProvider(), request, now=now)
    debate = run_tradingagents_debate(
        TradingAgentsConfig(
            enabled=False,
            ref="main",
            llm_provider="openai",
            results_dir=ROOT / "data" / "tradingagents" / "results",
            cache_dir=ROOT / "data" / "tradingagents" / "cache",
            memory_dir=ROOT / "data" / "tradingagents" / "memory",
            allow_execution=False,
        ),
        TradingAgentsPacketRequest(symbol="US.TEST"),
        evidence_pack,
        fixture=True,
    )
    packet = build_decision_packet(
        TradingAgentsPacketRequest(symbol="US.TEST"),
        evidence_pack,
        debate,
        source_ref="fixture",
    )
    sections = decision_packet_sections(packet)
    rendered = "\n".join(str(section) for section in sections)

    assert "Desk View" in rendered
    assert "BUY" not in rendered.upper()
    assert "SELL" not in rendered.upper()
    assert "EXECUTE" not in rendered.upper()
