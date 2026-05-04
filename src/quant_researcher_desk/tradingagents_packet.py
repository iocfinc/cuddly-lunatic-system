"""TradingAgents research packet boundaries for Quant Researcher Desk."""

from __future__ import annotations

import dataclasses
import datetime as dt
import html
import json
import os
import pathlib
import re
from dataclasses import dataclass
from typing import Any

from quant_researcher_desk.moomoo_options_report import RISK_NOTE
from quant_researcher_desk.options_research import (
    FixtureOptionsResearchProvider,
    OptionsResearchProvider,
    OptionsResearchReport,
    OptionsResearchRequest,
    build_options_research_report,
    format_money,
    format_pct,
)


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
        allow_execution=_env_flag(env_values.get("TRADINGAGENTS_ALLOW_EXECUTION"), default=False),
    )


def build_desk_evidence_pack(
    provider: OptionsResearchProvider,
    request: OptionsResearchRequest,
    now: dt.datetime | None = None,
) -> DeskEvidencePack:
    report = build_options_research_report(provider, request, now=now)
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


def _normalize_label(text: str, report: OptionsResearchReport) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ("strong buy", "buy", "long")):
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

    required_key = _required_llm_env_key(config.llm_provider)
    if required_key and not os.environ.get(required_key):
        raise TradingAgentsIntegrationError(
            f"TradingAgents requires {required_key} for llm_provider={config.llm_provider}."
        )

    try:
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

    graph = TradingAgentsGraph(debug=False, config=tradingagents_config)
    analysis_date = packet_request.analysis_date or evidence_pack.generated_at.date().isoformat()
    _, decision = graph.propagate(packet_request.symbol, analysis_date)
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
