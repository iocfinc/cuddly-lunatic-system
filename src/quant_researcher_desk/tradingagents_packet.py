"""TradingAgents research packet boundaries for Quant Researcher Desk."""

from __future__ import annotations

import dataclasses
import datetime as dt
import functools
import html
import json
import os
import pathlib
import pwd
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import Any

from quant_researcher_desk.execution_recovery import (
    normalize_debate_backend_error,
    normalize_options_report_error,
)
from quant_researcher_desk.moomoo_options_report import OptionsReportError, RISK_NOTE
from quant_researcher_desk.options_research import (
    FixtureOptionsResearchProvider,
    OptionsResearchProvider,
    OptionsResearchReport,
    OptionsResearchRequest,
    build_options_research_report,
    format_money,
    format_pct,
)

TRADINGAGENTS_DEFAULT_ANALYSTS = ["market", "news", "fundamentals"]


class TradingAgentsIntegrationError(Exception):
    """Raised when the optional TradingAgents integration cannot run."""


@dataclass(frozen=True)
class DeskEvidencePack:
    symbol: str
    generated_at: dt.datetime
    options_request: OptionsResearchRequest
    underlying_snapshot: dict[str, Any]
    options_chain_summary: dict[str, Any]
    iv_hv_context: dict[str, Any]
    scenario_outputs: list[dict[str, Any]]
    catalyst_context: dict[str, Any]
    sector_context: dict[str, Any]
    research_report: OptionsResearchReport


@dataclass(frozen=True)
class TradingAgentsPacketRequest:
    symbol: str
    analysis_date: str | None = None
    report_format: str = "pdf"
    post_to_telegram: bool = False


@dataclass(frozen=True)
class TradingAgentsConfig:
    enabled: bool
    ref: str
    llm_provider: str
    results_dir: pathlib.Path
    cache_dir: pathlib.Path
    memory_dir: pathlib.Path
    allow_execution: bool
    llm_backend: str
    codex_model: str
    codex_profile: str | None
    source_dir: pathlib.Path | None = None


@dataclass(frozen=True)
class AgentDebateResult:
    analyst_brief: str
    bullish_research: str
    bearish_research: str
    risk_assessment: str
    consensus_summary: str
    raw_decision: str
    warnings: list[str]
    provenance: dict[str, Any]


@dataclass(frozen=True)
class DecisionPacket:
    symbol: str
    generated_at: dt.datetime
    label: str
    title: str
    executive_summary: str
    evidence_pack: DeskEvidencePack
    debate_result: AgentDebateResult
    rationale: list[str]
    risk_flags: list[str]
    next_steps: list[str]
    source_ref: str


def _env_flag(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _repo_local_dir(root: pathlib.Path, *parts: str) -> pathlib.Path:
    return root.joinpath(*parts)


def _default_tradingagents_source_dir(root: pathlib.Path) -> pathlib.Path | None:
    return root.parent / "TradingAgents"


def _real_user_home() -> pathlib.Path:
    return pathlib.Path(pwd.getpwuid(os.getuid()).pw_dir)


def load_tradingagents_config(
    root: pathlib.Path,
    env: dict[str, str] | None = None,
    runtime_env: dict[str, str] | None = None,
) -> TradingAgentsConfig:
    env_values: dict[str, str] = {}
    if env:
        env_values.update(env)
    env_values.update(runtime_env or dict(os.environ))
    return TradingAgentsConfig(
        enabled=_env_flag(env_values.get("TRADINGAGENTS_ENABLED"), default=False),
        ref=env_values.get("TRADINGAGENTS_REF", "refs/tags/v0.2.4"),
        llm_provider=env_values.get("TRADINGAGENTS_LLM_PROVIDER", "openai"),
        results_dir=pathlib.Path(env_values.get("TRADINGAGENTS_RESULTS_DIR", _repo_local_dir(root, "data", "tradingagents", "results"))),
        cache_dir=pathlib.Path(env_values.get("TRADINGAGENTS_CACHE_DIR", _repo_local_dir(root, "data", "tradingagents", "cache"))),
        memory_dir=pathlib.Path(env_values.get("TRADINGAGENTS_MEMORY_DIR", _repo_local_dir(root, "data", "tradingagents", "memory"))),
        source_dir=pathlib.Path(source_dir).expanduser() if (source_dir := env_values.get("TRADINGAGENTS_SOURCE_DIR")) else _default_tradingagents_source_dir(root),
        allow_execution=_env_flag(env_values.get("TRADINGAGENTS_ALLOW_EXECUTION"), default=False),
        llm_backend=env_values.get("TRADINGAGENTS_LLM_BACKEND", "api").strip().lower() or "api",
        codex_model=env_values.get("TRADINGAGENTS_CODEX_MODEL", "gpt-5.4"),
        codex_profile=(env_values.get("TRADINGAGENTS_CODEX_PROFILE") or "").strip() or None,
    )


def build_desk_evidence_pack(
    provider: OptionsResearchProvider,
    request: OptionsResearchRequest,
    now: dt.datetime | None = None,
) -> DeskEvidencePack:
    try:
        report = build_options_research_report(provider, request, now=now)
    except OptionsReportError as exc:
        raise normalize_options_report_error(request.symbol, "evidence_pack", exc) from exc
    base_iv_rows = [
        {
            "price_shock_pct": row.price_shock_pct,
            "iv_shift_pct": row.iv_shift_pct,
            "underlying_price": row.underlying_price,
            "option_value": row.option_value,
            "profit_loss": row.profit_loss,
        }
        for row in report.scenario_rows
    ]
    market = request.symbol.split(".", 1)[0] if "." in request.symbol else "US"
    return DeskEvidencePack(
        symbol=report.symbol,
        generated_at=report.generated_at,
        options_request=request,
        underlying_snapshot={
            "symbol": report.symbol,
            "underlying_price": report.underlying_price,
            "generated_at": report.generated_at.isoformat(),
        },
        options_chain_summary={
            "selected_contract": report.contract.code,
            "option_type": report.contract.option_type,
            "strike": report.contract.strike,
            "expiry": report.contract.expiry,
            "market_price": report.contract.market_price,
            "open_interest": report.contract.open_interest,
            "volume": report.contract.volume,
        },
        iv_hv_context={
            "implied_volatility": report.implied_volatility_used,
            "historical_volatility": report.historical_volatility,
            "volatility_gap": report.implied_volatility_used - report.historical_volatility,
            "model_edge_pct": report.model_edge_pct,
        },
        scenario_outputs=base_iv_rows,
        catalyst_context={
            "phase": report.earnings.phase,
            "next_date": report.earnings.next_date,
            "summary": report.earnings.summary,
        },
        sector_context={
            "market": market,
            "summary": (
                f"{market} sector context is currently repo-owned and lightweight for {report.symbol}. "
                "The debate engine consumes the desk packet as context, but sector truth remains in naval-analyst providers."
            ),
        },
        research_report=report,
    )


def _sanitize_research_text(text: str) -> str:
    replacements = {
        r"\bbuy\b": "research candidate",
        r"\bsell\b": "reject",
        r"\bexecute\b": "publish",
        r"\bshort\b": "negative thesis",
        r"\border\b": "packet",
        r"\btrade\b": "research plan",
        r"\btrader\b": "decision desk",
        r"\bportfolio manager\b": "review lead",
    }
    clean = text
    for pattern, replacement in replacements.items():
        clean = re.sub(pattern, replacement, clean, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", clean).strip()


def _required_llm_env_key(provider: str) -> str | None:
    return {
        "abacus": "ABACUS_API_KEY",
        "openai": "OPENAI_API_KEY",
        "google": "GOOGLE_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "xai": "XAI_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "qwen": "DASHSCOPE_API_KEY",
        "glm": "ZHIPU_API_KEY",
        "azure": "AZURE_OPENAI_API_KEY",
    }.get(provider.lower())


def _upstream_tradingagents_symbol(symbol: str) -> str:
    text = symbol.strip().upper()
    if text.startswith("US.") and len(text) > 3:
        return text.split(".", 1)[1]
    return symbol


def _normalize_label(text: str, report: OptionsResearchReport) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ("strong buy", "buy", "long", "candidate")):
        return "Research Candidate"
    if any(token in lowered for token in ("sell", "short", "avoid", "reject")):
        return "Reject"
    if any(token in lowered for token in ("hold", "watch", "monitor")):
        return "Watchlist"
    if report.verdict in {"Research Candidate", "Watchlist", "Reject"}:
        return report.verdict
    return "Needs Human Review"


def _fixture_debate(evidence_pack: DeskEvidencePack) -> AgentDebateResult:
    report = evidence_pack.research_report
    volatility_gap = evidence_pack.iv_hv_context["volatility_gap"]
    return AgentDebateResult(
        analyst_brief=_sanitize_research_text(
            f"{report.symbol} is being reviewed through a bounded research packet. The selected contract is "
            f"{report.contract.code} with IV at {format_pct(report.implied_volatility_used)} and HV at "
            f"{format_pct(report.historical_volatility)}."
        ),
        bullish_research=_sanitize_research_text(
            f"The constructive case is that model value and scenario shape keep the contract on the desk as a "
            f"{report.verdict.lower()} while liquidity remains acceptable."
        ),
        bearish_research=_sanitize_research_text(
            "The opposing case is that catalyst timing and premium already embed a large share of the move, "
            "so downside to thesis quality can arrive even if direction is right."
        ),
        risk_assessment=_sanitize_research_text(
            f"Volatility gap is {format_pct(volatility_gap)}. Earnings timing, spread discipline, and the "
            "need for human sizing review remain the dominant controls."
        ),
        consensus_summary=_sanitize_research_text(
            f"Consensus: keep {report.symbol} in a research-only packet with explicit risk framing and no execution semantics."
        ),
        raw_decision=report.verdict,
        warnings=list(report.risks),
        provenance={"mode": "fixture", "provider": "naval-analyst"},
    )


def _codex_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "analyst_brief",
            "bullish_research",
            "bearish_research",
            "risk_assessment",
            "consensus_summary",
            "raw_decision",
            "warnings",
        ],
        "properties": {
            "analyst_brief": {"type": "string"},
            "bullish_research": {"type": "string"},
            "bearish_research": {"type": "string"},
            "risk_assessment": {"type": "string"},
            "consensus_summary": {"type": "string"},
            "raw_decision": {"type": "string"},
            "warnings": {"type": "array", "items": {"type": "string"}},
        },
    }


def _codex_prompt(packet_request: TradingAgentsPacketRequest, evidence_pack: DeskEvidencePack) -> str:
    report = evidence_pack.research_report
    prompt_payload = {
        "symbol": packet_request.symbol,
        "analysis_date": packet_request.analysis_date or evidence_pack.generated_at.date().isoformat(),
        "evidence_pack": dataclasses.asdict(evidence_pack),
        "instructions": [
            "You are producing a bounded research debate for Quant Researcher Desk.",
            "Use research-only language. Do not use BUY, SELL, EXECUTE, order submission, or broker-style phrasing.",
            "Return JSON matching the provided schema.",
            "raw_decision should be a short lowercase research outcome such as watch, reject, candidate, or review.",
        ],
        "style": "Professional desk note. State evidence, interpretation, and risk.",
        "non_goals": [
            "No broker connectivity",
            "No trade execution",
            "No portfolio instructions",
        ],
        "reference_metrics": {
            "selected_contract": report.contract.code,
            "underlying_price": report.underlying_price,
            "market_price": report.contract.market_price,
            "iv": report.implied_volatility_used,
            "hv": report.historical_volatility,
            "verdict": report.verdict,
        },
    }
    return json.dumps(prompt_payload, indent=2, default=_json_default)


def _codex_backend_debate(
    config: TradingAgentsConfig,
    packet_request: TradingAgentsPacketRequest,
    evidence_pack: DeskEvidencePack,
) -> AgentDebateResult:
    config.results_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="tradingagents-codex-", dir=str(config.results_dir)) as tmp_dir:
        tmp_path = pathlib.Path(tmp_dir)
        schema_path = tmp_path / "schema.json"
        output_path = tmp_path / "last-message.json"
        schema_path.write_text(json.dumps(_codex_output_schema(), indent=2), encoding="utf-8")

        cmd = [
            "codex",
            "exec",
            "-m",
            config.codex_model,
            "-C",
            str(pathlib.Path(__file__).resolve().parents[2]),
            "--sandbox",
            "read-only",
            "--output-schema",
            str(schema_path),
            "-o",
            str(output_path),
            "-",
        ]
        if config.codex_profile:
            cmd[2:2] = ["-p", config.codex_profile]

        env = dict(os.environ)
        env["TRADINGAGENTS_CACHE_DIR"] = str(config.cache_dir)
        env["TRADINGAGENTS_MEMORY_DIR"] = str(config.memory_dir)
        env["TRADINGAGENTS_MEMORY_LOG_PATH"] = str(config.memory_dir / "trading_memory.md")
        env["CODEX_HOME"] = env.get("CODEX_HOME", str(_real_user_home() / ".codex"))

        try:
            subprocess.run(
                cmd,
                input=_codex_prompt(packet_request, evidence_pack),
                text=True,
                capture_output=True,
                check=True,
                cwd=str(pathlib.Path(__file__).resolve().parents[2]),
                env=env,
            )
        except FileNotFoundError as exc:
            raise TradingAgentsIntegrationError("codex exec is not available on PATH.") from exc
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            stdout = (exc.stdout or "").strip()
            detail = stderr or stdout or str(exc)
            raise TradingAgentsIntegrationError(f"codex exec failed: {detail}") from exc

        if not output_path.exists():
            raise TradingAgentsIntegrationError("codex exec did not write the expected JSON output file.")

        try:
            payload = json.loads(output_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise TradingAgentsIntegrationError("codex exec returned non-JSON output despite the schema contract.") from exc

    warnings = payload.get("warnings")
    if not isinstance(warnings, list):
        warnings = [str(warnings)] if warnings else []

    return AgentDebateResult(
        analyst_brief=_sanitize_research_text(str(payload.get("analyst_brief", ""))),
        bullish_research=_sanitize_research_text(str(payload.get("bullish_research", ""))),
        bearish_research=_sanitize_research_text(str(payload.get("bearish_research", ""))),
        risk_assessment=_sanitize_research_text(str(payload.get("risk_assessment", ""))),
        consensus_summary=_sanitize_research_text(str(payload.get("consensus_summary", ""))),
        raw_decision=str(payload.get("raw_decision", "")),
        warnings=[_sanitize_research_text(str(item)) for item in warnings],
        provenance={"mode": "live", "provider": "codex", "model": config.codex_model},
    )


def _api_backend_debate(
    config: TradingAgentsConfig,
    packet_request: TradingAgentsPacketRequest,
    evidence_pack: DeskEvidencePack,
) -> AgentDebateResult:
    required_key = _required_llm_env_key(config.llm_provider)
    if required_key and not os.environ.get(required_key):
        raise TradingAgentsIntegrationError(
            f"TradingAgents requires {required_key} for llm_provider={config.llm_provider}."
        )

    try:
        if config.source_dir and str(config.source_dir) not in sys.path:
            sys.path.insert(0, str(config.source_dir))
        from tradingagents.default_config import DEFAULT_CONFIG  # type: ignore[import-not-found]
        from tradingagents.graph.trading_graph import TradingAgentsGraph  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise TradingAgentsIntegrationError(
            "TradingAgents dependency is not installed. Install the official TauricResearch/TradingAgents source "
            f"at ref {config.ref} and retry."
        ) from exc

    config.cache_dir.mkdir(parents=True, exist_ok=True)
    config.memory_dir.mkdir(parents=True, exist_ok=True)
    config.results_dir.mkdir(parents=True, exist_ok=True)
    os.environ["TRADINGAGENTS_CACHE_DIR"] = str(config.cache_dir)
    os.environ["TRADINGAGENTS_MEMORY_DIR"] = str(config.memory_dir)
    os.environ["TRADINGAGENTS_MEMORY_LOG_PATH"] = str(config.memory_dir / "trading_memory.md")

    tradingagents_config = DEFAULT_CONFIG.copy()
    tradingagents_config["llm_provider"] = config.llm_provider
    tradingagents_config["checkpoint_enabled"] = False
    tradingagents_config["deep_think_llm"] = tradingagents_config.get("deep_think_llm")
    tradingagents_config["quick_think_llm"] = tradingagents_config.get("quick_think_llm")

    graph = TradingAgentsGraph(
        selected_analysts=TRADINGAGENTS_DEFAULT_ANALYSTS,
        debug=False,
        config=tradingagents_config,
    )
    analysis_date = packet_request.analysis_date or evidence_pack.generated_at.date().isoformat()
    upstream_symbol = _upstream_tradingagents_symbol(packet_request.symbol)
    _, decision = graph.propagate(upstream_symbol, analysis_date)
    raw_text = decision if isinstance(decision, str) else json.dumps(decision, sort_keys=True, default=str)
    safe_text = _sanitize_research_text(raw_text)

    return AgentDebateResult(
        analyst_brief=_sanitize_research_text(
            f"{packet_request.symbol} review completed through the optional TradingAgents adapter on {analysis_date}."
        ),
        bullish_research=safe_text[:500],
        bearish_research="Raw TradingAgents output stored in repo-local artifacts for audit.",
        risk_assessment="Live adapter ran successfully, but market-data truth remains owned by naval-analyst inputs.",
        consensus_summary=safe_text[:500],
        raw_decision=raw_text,
        warnings=["Review the stored raw decision payload before sharing externally."],
        provenance={"mode": "live", "provider": "TradingAgents", "ref": config.ref},
    )


def _llm_backend_dispatcher(fn):  # type: ignore[no-untyped-def]
    @functools.wraps(fn)
    def wrapper(
        config: TradingAgentsConfig,
        packet_request: TradingAgentsPacketRequest,
        evidence_pack: DeskEvidencePack,
    ) -> AgentDebateResult:
        if config.llm_backend == "codex":
            return _codex_backend_debate(config, packet_request, evidence_pack)
        return fn(config, packet_request, evidence_pack)

    return wrapper


@_llm_backend_dispatcher
def _run_live_tradingagents_debate(
    config: TradingAgentsConfig,
    packet_request: TradingAgentsPacketRequest,
    evidence_pack: DeskEvidencePack,
) -> AgentDebateResult:
    return _api_backend_debate(config, packet_request, evidence_pack)


def run_tradingagents_debate(
    config: TradingAgentsConfig,
    packet_request: TradingAgentsPacketRequest,
    evidence_pack: DeskEvidencePack,
    fixture: bool = False,
) -> AgentDebateResult:
    if fixture:
        return _fixture_debate(evidence_pack)
    if not config.enabled:
        raise TradingAgentsIntegrationError(
            "TradingAgents is disabled. Set TRADINGAGENTS_ENABLED=true to enable the optional adapter."
        )
    if config.allow_execution:
        raise TradingAgentsIntegrationError(
            "TRADINGAGENTS_ALLOW_EXECUTION must remain false in naval-analyst. This integration is research-only."
        )
    return _run_live_tradingagents_debate(config, packet_request, evidence_pack)


def run_tradingagents_debate_for_symbol(
    config: TradingAgentsConfig,
    packet_request: TradingAgentsPacketRequest,
    evidence_pack: DeskEvidencePack,
    fixture: bool = False,
) -> AgentDebateResult:
    try:
        return run_tradingagents_debate(config, packet_request, evidence_pack, fixture=fixture)
    except TradingAgentsIntegrationError as exc:
        raise normalize_debate_backend_error(packet_request.symbol, "debate_backend", exc) from exc


def build_decision_packet(
    packet_request: TradingAgentsPacketRequest,
    evidence_pack: DeskEvidencePack,
    debate_result: AgentDebateResult,
    source_ref: str,
) -> DecisionPacket:
    report = evidence_pack.research_report
    label = _normalize_label(debate_result.raw_decision, report)
    executive_summary = _sanitize_research_text(
        f"{report.symbol} is classified as {label}. The packet combines naval-analyst market context, "
        f"scenario work, and a bounded research debate around {report.contract.code}."
    )
    rationale = [
        _sanitize_research_text(debate_result.analyst_brief),
        _sanitize_research_text(debate_result.consensus_summary),
        _sanitize_research_text(
            f"Model edge is {format_pct(report.model_edge_pct)} with IV/HV at "
            f"{format_pct(report.implied_volatility_used)}/{format_pct(report.historical_volatility)}."
        ),
    ]
    next_steps = [
        "Confirm catalyst timing and whether the option window overlaps the event.",
        "Re-check liquidity and spread quality before treating the packet as actionable research.",
        "Keep human review in the loop before any portfolio decision outside this repo.",
    ]
    return DecisionPacket(
        symbol=packet_request.symbol,
        generated_at=evidence_pack.generated_at,
        label=label,
        title=f"{packet_request.symbol} Decision Packet",
        executive_summary=executive_summary,
        evidence_pack=evidence_pack,
        debate_result=debate_result,
        rationale=rationale,
        risk_flags=[_sanitize_research_text(risk) for risk in report.risks],
        next_steps=next_steps,
        source_ref=source_ref,
    )


def decision_packet_sections(packet: DecisionPacket) -> list[dict[str, object]]:
    report = packet.evidence_pack.research_report
    scenario_rows = [
        {
            "price_shock": format_pct(row["price_shock_pct"]),
            "iv_shift": format_pct(row["iv_shift_pct"]),
            "underlying": format_money(row["underlying_price"]),
            "option_value": format_money(row["option_value"]),
            "profit_loss": format_money(row["profit_loss"]),
        }
        for row in packet.evidence_pack.scenario_outputs
    ]
    return [
        {"title": "Desk View", "content": packet.executive_summary},
        {"title": "Research Debate", "items": packet.rationale},
        {
            "title": "Evidence Pack",
            "table": [
                {"metric": "Symbol", "value": packet.symbol},
                {"metric": "Label", "value": packet.label},
                {"metric": "Contract", "value": report.contract.code},
                {"metric": "Underlying", "value": format_money(report.underlying_price)},
                {"metric": "Market Price", "value": format_money(report.contract.market_price)},
                {"metric": "Model Edge", "value": format_pct(report.model_edge_pct)},
                {"metric": "IV / HV", "value": f"{format_pct(report.implied_volatility_used)} / {format_pct(report.historical_volatility)}"},
                {"metric": "Catalyst", "value": packet.evidence_pack.catalyst_context["summary"]},
            ],
        },
        {"title": "Scenario Matrix", "table": scenario_rows},
        {"title": "Risk Register", "items": packet.risk_flags},
        {"title": "Next Steps", "items": packet.next_steps},
        {"title": "Research Boundary", "content": RISK_NOTE},
    ]


def format_decision_packet_telegram_html(packet: DecisionPacket) -> str:
    generated = packet.generated_at.strftime("%Y-%m-%d %H:%M %Z").strip()
    report = packet.evidence_pack.research_report
    lines = [
        f"<b>{html.escape(packet.symbol)} Decision Packet</b>",
        f"<code>{html.escape(generated)}</code>",
        f"Label: <b>{html.escape(packet.label)}</b>",
        f"Contract: <code>{html.escape(report.contract.code)}</code>",
        f"IV/HV: <code>{html.escape(format_pct(report.implied_volatility_used))}/{html.escape(format_pct(report.historical_volatility))}</code>",
        "",
        html.escape(packet.executive_summary[:360]),
        "",
        "Detailed packet attached.",
        html.escape(RISK_NOTE),
    ]
    return "\n".join(lines)


def _json_default(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    if isinstance(value, pathlib.Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9-]+", "-", value.strip()).strip("-").lower() or "packet"


def persist_decision_packet(packet: DecisionPacket, results_dir: pathlib.Path) -> pathlib.Path:
    results_dir.mkdir(parents=True, exist_ok=True)
    output_path = results_dir / f"{_slug(packet.title)}.json"
    output_path.write_text(json.dumps(packet, indent=2, default=_json_default), encoding="utf-8")
    return output_path


def fixture_decision_packet(
    symbol: str,
    now: dt.datetime | None = None,
) -> DecisionPacket:
    request = OptionsResearchRequest(symbol=symbol)
    evidence_pack = build_desk_evidence_pack(FixtureOptionsResearchProvider(), request, now=now)
    debate_result = _fixture_debate(evidence_pack)
    return build_decision_packet(TradingAgentsPacketRequest(symbol=symbol), evidence_pack, debate_result, source_ref="fixture")
