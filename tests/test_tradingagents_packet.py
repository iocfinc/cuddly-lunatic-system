from __future__ import annotations

import datetime as dt
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quant_researcher_desk.options_research import FixtureOptionsResearchProvider, OptionsResearchRequest
from quant_researcher_desk.tradingagents_packet import (
    AgentDebateResult,
    TradingAgentsConfig,
    TradingAgentsIntegrationError,
    TradingAgentsPacketRequest,
    _codex_backend_debate,
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
    assert config.llm_backend == "api"
    assert config.codex_model == "gpt-5.4"
    assert config.codex_profile is None


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


def test_load_tradingagents_config_reads_codex_backend_settings(tmp_path: pathlib.Path) -> None:
    config = load_tradingagents_config(
        ROOT,
        env={
            "TRADINGAGENTS_ENABLED": "true",
            "TRADINGAGENTS_LLM_BACKEND": "codex",
            "TRADINGAGENTS_CODEX_MODEL": "gpt-5.4",
            "TRADINGAGENTS_CODEX_PROFILE": "research",
            "TRADINGAGENTS_RESULTS_DIR": str(tmp_path / "results"),
            "TRADINGAGENTS_CACHE_DIR": str(tmp_path / "cache"),
            "TRADINGAGENTS_MEMORY_DIR": str(tmp_path / "memory"),
        },
    )

    assert config.enabled is True
    assert config.llm_backend == "codex"
    assert config.codex_model == "gpt-5.4"
    assert config.codex_profile == "research"


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
            llm_backend="api",
            codex_model="gpt-5.4",
            codex_profile=None,
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
                llm_backend="api",
                codex_model="gpt-5.4",
                codex_profile=None,
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
                llm_backend="api",
                codex_model="gpt-5.4",
                codex_profile=None,
            ),
            TradingAgentsPacketRequest(symbol="US.TEST"),
            evidence_pack,
            fixture=False,
        )


def test_codex_backend_debate_uses_headless_codex_json_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    now = dt.datetime(2026, 5, 4, 9, 30, tzinfo=dt.timezone.utc)
    evidence_pack = build_desk_evidence_pack(
        FixtureOptionsResearchProvider(),
        OptionsResearchRequest(symbol="US.TEST"),
        now=now,
    )
    config = TradingAgentsConfig(
        enabled=True,
        ref="refs/tags/v0.2.4",
        llm_provider="openai",
        results_dir=tmp_path / "results",
        cache_dir=tmp_path / "cache",
        memory_dir=tmp_path / "memory",
        allow_execution=False,
        llm_backend="codex",
        codex_model="gpt-5.4",
        codex_profile="research",
    )
    packet_request = TradingAgentsPacketRequest(symbol="US.TEST")
    captured: dict[str, object] = {}

    def fake_run(cmd, input=None, text=None, capture_output=None, check=None, cwd=None, env=None):  # type: ignore[no-untyped-def]
        captured["cmd"] = cmd
        captured["input"] = input
        captured["cwd"] = cwd
        captured["env"] = env
        output_path = pathlib.Path(cmd[cmd.index("-o") + 1])
        output_path.write_text(
            '{"analyst_brief":"BUY strength","bullish_research":"Constructive setup","bearish_research":"Catalyst risk","risk_assessment":"Needs review","consensus_summary":"Watch closely","raw_decision":"watch","warnings":["spread risk"]}',
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok":true}', stderr="")

    monkeypatch.setattr("quant_researcher_desk.tradingagents_packet.subprocess.run", fake_run)

    result = _codex_backend_debate(config, packet_request, evidence_pack)

    assert isinstance(result, AgentDebateResult)
    assert result.raw_decision == "watch"
    assert result.analyst_brief == "research candidate strength"
    assert result.provenance["provider"] == "codex"
    assert captured["cwd"] == str(ROOT)
    assert "--output-schema" in captured["cmd"]
    assert "-m" in captured["cmd"]
    assert "gpt-5.4" in captured["cmd"]
    assert "-p" in captured["cmd"]
    assert "research" in captured["cmd"]
    assert "--ask-for-approval" not in captured["cmd"]
    assert str(captured["env"]["CODEX_HOME"]).endswith("/.codex")
    assert "US.TEST" in str(captured["input"])


def test_run_tradingagents_debate_codex_backend_wraps_headless_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = dt.datetime(2026, 5, 4, 9, 30, tzinfo=dt.timezone.utc)
    evidence_pack = build_desk_evidence_pack(
        FixtureOptionsResearchProvider(),
        OptionsResearchRequest(symbol="US.TEST"),
        now=now,
    )

    def fake_codex_backend(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise TradingAgentsIntegrationError("codex exec failed: model unavailable")

    monkeypatch.setattr("quant_researcher_desk.tradingagents_packet._codex_backend_debate", fake_codex_backend)

    with pytest.raises(TradingAgentsIntegrationError, match="codex exec failed: model unavailable"):
        run_tradingagents_debate(
            TradingAgentsConfig(
                enabled=True,
                ref="refs/tags/v0.2.4",
                llm_provider="openai",
                results_dir=ROOT / "data" / "tradingagents" / "results",
                cache_dir=ROOT / "data" / "tradingagents" / "cache",
                memory_dir=ROOT / "data" / "tradingagents" / "memory",
                allow_execution=False,
                llm_backend="codex",
                codex_model="gpt-5.4",
                codex_profile="research",
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
            llm_backend="api",
            codex_model="gpt-5.4",
            codex_profile=None,
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
