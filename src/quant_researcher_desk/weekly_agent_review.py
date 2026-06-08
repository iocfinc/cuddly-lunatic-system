"""Weekly packet Agent Review integration via direct OpenRouter calls."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable


SYSTEM_PROMPT = """You are the Agent Review reviewer for Quant Researcher Desk.

Role:
You are a portfolio and risk reviewer. You review a weekly top-10 options packet after the deterministic screen and single-name tear sheets have already been built. Your job is to synthesize, reflect, deliberate, and propose one research-grade trading idea for human review.

Hard rules:
- Do not claim this is financial advice.
- Do not issue an order, execution instruction, or automated-trading directive.
- Treat every candidate as a research packet requiring human confirmation.
- Prefer no idea over a weak idea.
- Use only the evidence in the supplied JSON.
- If evidence is insufficient, say exactly what is missing.
- Penalize thin liquidity, wide spread proxies, rich premium, weak model confidence, stale catalyst context, and unclear event timing.
- Respect deterministic reviewer flags; you may override their ranking only if you explain why.
- The proposed idea must include instrument, thesis, invalidation, risk controls, and follow-up checks.

Process:
1. Synthesize the whole top-10 list.
2. Reflect on portfolio-level risk, duplication, event concentration, and liquidity.
3. Deliberate between the strongest candidates and explain the tradeoff.
4. Propose one trading idea for human review, or propose no action if none clears the bar.

Return JSON only with this schema:
{
  "synthesis": "string",
  "reflection": "string",
  "deliberation": "string",
  "proposed_trading_idea": "string",
  "top_candidate": {
    "rank": "string",
    "symbol": "string",
    "option_code": "string",
    "reason": "string"
  },
  "watchouts": ["string"],
  "risk_controls": ["string"],
  "follow_up_checks": ["string"]
}
"""


@dataclass(frozen=True)
class WeeklyAgentReviewConfig:
    enabled: bool = False
    provider: str = "openrouter"
    base_url: str = "https://openrouter.ai/api/v1"
    model: str = "deepseek/deepseek-v4-flash"
    fallback_model: str = "tencent/hy3-preview"
    timeout_seconds: int = 90
    max_tokens: int = 1800
    temperature: float = 0.2
    api_key: str | None = None


@dataclass(frozen=True)
class WeeklyAgentReviewResult:
    model_used: str
    fallback_used: bool
    synthesis: str
    reflection: str
    deliberation: str
    proposed_trading_idea: str
    top_candidate: dict[str, str]
    watchouts: list[str]
    risk_controls: list[str]
    follow_up_checks: list[str]
    warnings: list[str]
    raw_response: dict[str, Any]


class WeeklyAgentReviewError(Exception):
    def __init__(self, message: str, warnings: list[str] | None = None) -> None:
        super().__init__(message)
        self.warnings = list(warnings or [message])


def load_weekly_agent_review_config(env: dict[str, str] | None = None) -> WeeklyAgentReviewConfig:
    values = env or os.environ
    api_key = (values.get("OPENROUTER_API_KEY") or "").strip() or None
    return WeeklyAgentReviewConfig(
        enabled=(values.get("WEEKLY_AGENT_REVIEW_ENABLED", "false").strip().lower() == "true"),
        provider=(values.get("WEEKLY_AGENT_REVIEW_PROVIDER") or "openrouter").strip().lower(),
        base_url=(values.get("WEEKLY_AGENT_REVIEW_BASE_URL") or "https://openrouter.ai/api/v1").strip(),
        model=(values.get("WEEKLY_AGENT_REVIEW_MODEL") or "deepseek/deepseek-v4-flash").strip(),
        fallback_model=(values.get("WEEKLY_AGENT_REVIEW_FALLBACK_MODEL") or "tencent/hy3-preview").strip(),
        timeout_seconds=int(values.get("WEEKLY_AGENT_REVIEW_TIMEOUT_SECONDS", "90")),
        max_tokens=int(values.get("WEEKLY_AGENT_REVIEW_MAX_TOKENS", "1800")),
        temperature=float(values.get("WEEKLY_AGENT_REVIEW_TEMPERATURE", "0.2")),
        api_key=api_key,
    )


def build_weekly_agent_review_evidence(packet: Any) -> dict[str, Any]:
    weekly_result = packet.weekly_result
    shortlist_rows = []
    per_rank = []
    for tearsheet in packet.tearsheets:
        report = tearsheet.report
        base_iv_rows = [
            {
                "price_shock_pct": round(row.price_shock_pct, 4),
                "underlying_price": round(row.underlying_price, 4),
                "option_value": round(row.option_value, 4),
                "profit_loss": round(row.profit_loss, 4),
            }
            for row in report.scenario_rows
            if abs(row.iv_shift_pct) < 0.0001
        ]
        shortlist_rows.append(
            {
                "rank": tearsheet.rank,
                "symbol": report.symbol,
                "side": report.contract.option_type,
                "expiry": report.contract.expiry,
                "strike": round(report.contract.strike, 4),
                "premium": round(report.contract.market_price, 4),
                "fair_value_gap_pct": round(report.fair_value_gap_pct, 4),
                "valuation_view": report.valuation_view,
                "verdict": report.verdict,
                "review_status": getattr(weekly_result.ranked_options[tearsheet.rank - 1], "review_status", "Not Reviewed"),
                "review_flags": list(getattr(weekly_result.ranked_options[tearsheet.rank - 1], "review_flags", ())),
                "trend_regime": getattr(weekly_result.ranked_options[tearsheet.rank - 1], "trend_regime", "mixed"),
                "stock_direction": getattr(weekly_result.ranked_options[tearsheet.rank - 1], "stock_direction", "no_trade"),
                "alignment_status": getattr(weekly_result.ranked_options[tearsheet.rank - 1], "alignment_status", "Unknown"),
            }
        )
        per_rank.append(
            {
                "rank": tearsheet.rank,
                "symbol": report.symbol,
                "option_code": report.contract.code,
                "side": report.contract.option_type,
                "expiry": report.contract.expiry,
                "strike": round(report.contract.strike, 4),
                "premium": round(report.contract.market_price, 4),
                "fair_value_gap_pct": round(report.fair_value_gap_pct, 4),
                "valuation_view": report.valuation_view,
                "iv_hv": {
                    "implied_volatility": round(report.implied_volatility_used, 4),
                    "historical_volatility": round(report.historical_volatility, 4),
                },
                "verdict": report.verdict,
                "deterministic_review": {
                    "status": getattr(weekly_result.ranked_options[tearsheet.rank - 1], "review_status", "Not Reviewed"),
                    "flags": list(getattr(weekly_result.ranked_options[tearsheet.rank - 1], "review_flags", ())),
                    "notes": getattr(weekly_result.ranked_options[tearsheet.rank - 1], "review_notes", ""),
                },
                "stock_context": {
                    "trend_regime": getattr(weekly_result.ranked_options[tearsheet.rank - 1], "trend_regime", "mixed"),
                    "direction": getattr(weekly_result.ranked_options[tearsheet.rank - 1], "stock_direction", "no_trade"),
                    "thesis_summary": getattr(weekly_result.ranked_options[tearsheet.rank - 1], "stock_review_summary", ""),
                    "invalidation": getattr(weekly_result.ranked_options[tearsheet.rank - 1], "invalidation", ""),
                    "catalyst_view": getattr(weekly_result.ranked_options[tearsheet.rank - 1], "catalyst_view", ""),
                    "alignment_status": getattr(weekly_result.ranked_options[tearsheet.rank - 1], "alignment_status", "Unknown"),
                    "review_confidence": getattr(weekly_result.ranked_options[tearsheet.rank - 1], "stock_review_confidence", ""),
                    "countertrend_risk": getattr(weekly_result.ranked_options[tearsheet.rank - 1], "countertrend_risk", ""),
                },
                "thesis": report.thesis,
                "risk_register": list(report.risks),
                "black_scholes_curve": report.black_scholes_curve,
                "monte_carlo_paths": report.monte_carlo_paths,
                "monte_carlo_distribution": report.monte_carlo_distribution,
                "scenario_shape": base_iv_rows,
            }
        )
    return {
        "packet_metadata": {
            "generated_at": packet.generated_at.isoformat(),
            "market": weekly_result.request.market,
            "shortlist_size": len(packet.tearsheets),
            "pricing_engine": weekly_result.pricing_engine,
        },
        "shortlist_context": {
            "deterministic_reviewer_summary": weekly_result.review_summary or "Deterministic reviewer summary unavailable.",
            "executive_summary": packet.executive_summary,
            "shortlist_table": shortlist_rows,
        },
        "ranked_evidence": per_rank,
    }


def request_weekly_agent_review(
    packet: Any,
    config: WeeklyAgentReviewConfig,
    *,
    urlopen: Callable[..., Any] | None = None,
) -> WeeklyAgentReviewResult:
    if not config.enabled:
        raise WeeklyAgentReviewError("Agent Review is disabled.")
    if config.provider != "openrouter":
        raise WeeklyAgentReviewError(f"Unsupported Agent Review provider: {config.provider}.")
    if not config.api_key:
        raise WeeklyAgentReviewError("Agent Review enabled but OPENROUTER_API_KEY is missing.")

    evidence = build_weekly_agent_review_evidence(packet)
    primary_warning: list[str] = []
    try:
        return _request_model_review(
            evidence,
            config=config,
            model=config.model,
            fallback_used=False,
            warnings=[],
            urlopen=urlopen or urllib.request.urlopen,
        )
    except WeeklyAgentReviewError as exc:
        primary_warning = exc.warnings
        if not config.fallback_model or config.fallback_model == config.model:
            raise
    try:
        return _request_model_review(
            evidence,
            config=config,
            model=config.fallback_model,
            fallback_used=True,
            warnings=primary_warning,
            urlopen=urlopen or urllib.request.urlopen,
        )
    except WeeklyAgentReviewError as exc:
        raise WeeklyAgentReviewError(
            "Agent Review failed for both primary and fallback models.",
            warnings=primary_warning + exc.warnings,
        ) from exc


def maybe_request_weekly_agent_review(
    packet: Any,
    config: WeeklyAgentReviewConfig,
    *,
    urlopen: Callable[..., Any] | None = None,
) -> tuple[WeeklyAgentReviewResult | None, list[str]]:
    if not config.enabled:
        return None, []
    try:
        result = request_weekly_agent_review(packet, config, urlopen=urlopen)
        return result, list(result.warnings)
    except WeeklyAgentReviewError as exc:
        return None, list(exc.warnings)


def _request_model_review(
    evidence: dict[str, Any],
    *,
    config: WeeklyAgentReviewConfig,
    model: str,
    fallback_used: bool,
    warnings: list[str],
    urlopen: Callable[..., Any],
) -> WeeklyAgentReviewResult:
    request_body = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Weekly packet evidence JSON:\n{json.dumps(evidence, indent=2)}"},
            ],
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "response_format": {"type": "json_object"},
        }
    ).encode("utf-8")
    endpoint = config.base_url.rstrip("/") + "/chat/completions"
    request = urllib.request.Request(
        endpoint,
        data=request_body,
        method="POST",
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=config.timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise WeeklyAgentReviewError(
            f"Agent Review request failed for model {model}: {exc}",
            warnings=warnings + [f"Agent Review request failed for model {model}: {exc}"],
        ) from exc

    try:
        content = _extract_assistant_content(payload)
        parsed = json.loads(_strip_code_fences(content))
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise WeeklyAgentReviewError(
            f"Agent Review returned invalid JSON for model {model}: {exc}",
            warnings=warnings + [f"Agent Review returned invalid JSON for model {model}: {exc}"],
        ) from exc
    return _parse_review_result(parsed, raw_response=payload, model=model, fallback_used=fallback_used, warnings=warnings)


def _extract_assistant_content(payload: dict[str, Any]) -> str:
    choices = payload["choices"]
    first = choices[0]
    content = first["message"]["content"]
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                parts.append(item["text"])
        if parts:
            return "".join(parts)
    raise KeyError("choices[0].message.content")


def _strip_code_fences(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _require_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise WeeklyAgentReviewError(f"Agent Review field {key} must be a string.")
    return value


def _require_string_list(payload: dict[str, Any], key: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise WeeklyAgentReviewError(f"Agent Review field {key} must be a list of strings.")
    return list(value)


def _parse_review_result(
    payload: dict[str, Any],
    *,
    raw_response: dict[str, Any],
    model: str,
    fallback_used: bool,
    warnings: list[str],
) -> WeeklyAgentReviewResult:
    if not isinstance(payload, dict):
        raise WeeklyAgentReviewError("Agent Review payload must be a JSON object.")
    top_candidate = payload.get("top_candidate")
    if not isinstance(top_candidate, dict):
        raise WeeklyAgentReviewError("Agent Review field top_candidate must be an object.")
    normalized_top_candidate = {
        key: str(top_candidate.get(key, ""))
        for key in ("rank", "symbol", "option_code", "reason")
    }
    return WeeklyAgentReviewResult(
        model_used=model,
        fallback_used=fallback_used,
        synthesis=_require_string(payload, "synthesis"),
        reflection=_require_string(payload, "reflection"),
        deliberation=_require_string(payload, "deliberation"),
        proposed_trading_idea=_require_string(payload, "proposed_trading_idea"),
        top_candidate=normalized_top_candidate,
        watchouts=_require_string_list(payload, "watchouts"),
        risk_controls=_require_string_list(payload, "risk_controls"),
        follow_up_checks=_require_string_list(payload, "follow_up_checks"),
        warnings=list(warnings),
        raw_response=raw_response,
    )
