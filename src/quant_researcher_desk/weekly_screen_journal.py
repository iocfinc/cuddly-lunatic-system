"""Weekly screen journal sync with per-option GPT-5.5 reviews."""

from __future__ import annotations

import concurrent.futures
import dataclasses
import datetime as dt
import json
import os
import pathlib
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Any

from quant_researcher_desk.notion_trade_journal import (
    NotionEntryPayload,
    _bulleted_list_blocks,
    _heading_block,
    _paragraph_blocks,
    _table_block_from_dict_rows,
)
from quant_researcher_desk.weekly_options_screener import (
    ScreenedOption,
    WeeklyScreenResult,
    gate_summary_rows,
    screen_report_sections,
    shortlist_rows,
    weekly_run_summary,
)


class WeeklyOptionAgentReviewError(Exception):
    """Raised when a single GPT option review cannot be completed."""


@dataclass(frozen=True)
class WeeklyOptionAgentReviewConfig:
    enabled: bool = False
    model: str = "gpt-5.5"
    top_k: int = 5
    concurrency: int = 3
    timeout_seconds: int = 120
    codex_profile: str | None = None


@dataclass(frozen=True)
class WeeklyOptionAgentReviewResult:
    option_code: str
    symbol: str
    model_used: str
    review_disposition: str
    summary: str
    why_this_contract: str
    main_risks: tuple[str, ...]
    invalidation: str
    follow_up_checks: tuple[str, ...]


@dataclass(frozen=True)
class WeeklyScreenJournalSyncConfig:
    notion_enabled: bool
    notion_dry_run: bool
    option_agent_review: WeeklyOptionAgentReviewConfig


@dataclass(frozen=True)
class WeeklyScreenOptionEntry:
    title: str
    date: str
    run_key: str
    run_path: str
    external_id: str
    screened_option: ScreenedOption
    rank: int
    review_result: WeeklyOptionAgentReviewResult | None
    review_error: str | None
    artifact_paths: tuple[str, ...]


@dataclass(frozen=True)
class WeeklyScreenRunEntry:
    title: str
    date: str
    run_key: str
    run_path: str
    external_id: str
    result: WeeklyScreenResult
    option_entries: tuple[WeeklyScreenOptionEntry, ...]
    artifact_paths: tuple[str, ...]
    review_warnings: tuple[str, ...]


def load_weekly_option_agent_review_config(env: dict[str, str] | None = None) -> WeeklyOptionAgentReviewConfig:
    values = env or os.environ
    return WeeklyOptionAgentReviewConfig(
        enabled=(values.get("WEEKLY_OPTION_AGENT_REVIEW_ENABLED", "false").strip().lower() == "true"),
        model=(values.get("WEEKLY_OPTION_AGENT_REVIEW_MODEL") or "gpt-5.5").strip() or "gpt-5.5",
        top_k=max(1, int(values.get("WEEKLY_OPTION_AGENT_REVIEW_TOP_K", "5"))),
        concurrency=max(1, int(values.get("WEEKLY_OPTION_AGENT_REVIEW_CONCURRENCY", "3"))),
        timeout_seconds=max(1, int(values.get("WEEKLY_OPTION_AGENT_REVIEW_TIMEOUT_SECONDS", "120"))),
        codex_profile=(values.get("WEEKLY_OPTION_AGENT_REVIEW_PROFILE") or "").strip() or None,
    )


def weekly_screen_run_external_id(run_key: str) -> str:
    return f"weekly-screen-run:{run_key}"


def weekly_screen_option_external_id(run_key: str, option_code: str) -> str:
    return f"weekly-screen-option:{run_key}:{option_code}"


def weekly_screen_run_key(result: WeeklyScreenResult) -> str:
    return result.generated_at.strftime("%Y%m%d_%H%M%S")


def select_weekly_screen_options_for_agent_review(
    result: WeeklyScreenResult,
    top_k: int,
) -> tuple[tuple[int, ScreenedOption], ...]:
    limit = max(0, top_k)
    return tuple((rank, option) for rank, option in enumerate(result.ranked_options[:limit], start=1))


def request_weekly_option_reviews(
    result: WeeklyScreenResult,
    config: WeeklyOptionAgentReviewConfig,
) -> tuple[dict[str, WeeklyOptionAgentReviewResult], dict[str, str]]:
    if not config.enabled:
        return {}, {}
    selected = select_weekly_screen_options_for_agent_review(result, config.top_k)
    if not selected:
        return {}, {}

    reviews: dict[str, WeeklyOptionAgentReviewResult] = {}
    failures: dict[str, str] = {}
    max_workers = min(max(1, config.concurrency), len(selected))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(_request_single_option_review, result, option, rank, config): option.option_code
            for rank, option in selected
        }
        for future in concurrent.futures.as_completed(future_map):
            option_code = future_map[future]
            try:
                review = future.result()
            except WeeklyOptionAgentReviewError as exc:
                failures[option_code] = str(exc)
                continue
            reviews[option_code] = review
    return reviews, failures


def _request_single_option_review(
    result: WeeklyScreenResult,
    option: ScreenedOption,
    rank: int,
    config: WeeklyOptionAgentReviewConfig,
) -> WeeklyOptionAgentReviewResult:
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory(prefix="weekly-option-review-") as tmp_dir:
        tmp_path = pathlib.Path(tmp_dir)
        schema_path = tmp_path / "schema.json"
        output_path = tmp_path / "last-message.json"
        schema_path.write_text(json.dumps(_option_review_output_schema(), indent=2), encoding="utf-8")
        cmd = [
            "codex",
            "exec",
            "-m",
            config.model,
            "-C",
            str(repo_root),
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
        env["CODEX_HOME"] = env.get("CODEX_HOME", str(pathlib.Path.home() / ".codex"))
        try:
            subprocess.run(
                cmd,
                input=_option_review_prompt(result, option, rank),
                text=True,
                capture_output=True,
                check=True,
                cwd=str(repo_root),
                env=env,
                timeout=config.timeout_seconds,
            )
        except FileNotFoundError as exc:
            raise WeeklyOptionAgentReviewError("codex exec is not available on PATH.") from exc
        except subprocess.TimeoutExpired as exc:
            raise WeeklyOptionAgentReviewError(
                f"codex exec timed out after {config.timeout_seconds}s for {option.option_code}."
            ) from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or "").strip() or (exc.stdout or "").strip() or str(exc)
            raise WeeklyOptionAgentReviewError(f"codex exec failed for {option.option_code}: {detail}") from exc
        if not output_path.exists():
            raise WeeklyOptionAgentReviewError(f"codex exec did not write JSON output for {option.option_code}.")
        try:
            payload = json.loads(output_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise WeeklyOptionAgentReviewError(f"codex exec returned non-JSON output for {option.option_code}.") from exc

    return WeeklyOptionAgentReviewResult(
        option_code=option.option_code,
        symbol=option.symbol,
        model_used=config.model,
        review_disposition=str(payload["review_disposition"]),
        summary=str(payload["summary"]),
        why_this_contract=str(payload["why_this_contract"]),
        main_risks=tuple(str(item) for item in payload["main_risks"]),
        invalidation=str(payload["invalidation"]),
        follow_up_checks=tuple(str(item) for item in payload["follow_up_checks"]),
    )


def _option_review_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "summary": {"type": "string"},
            "why_this_contract": {"type": "string"},
            "main_risks": {"type": "array", "items": {"type": "string"}},
            "invalidation": {"type": "string"},
            "follow_up_checks": {"type": "array", "items": {"type": "string"}},
            "review_disposition": {"type": "string"},
        },
        "required": [
            "summary",
            "why_this_contract",
            "main_risks",
            "invalidation",
            "follow_up_checks",
            "review_disposition",
        ],
    }


def _option_review_prompt(result: WeeklyScreenResult, option: ScreenedOption, rank: int) -> str:
    shortlist_context = [
        {
            "rank": index,
            "symbol": row["symbol"],
            "option_code": screened.option_code,
            "side": row["side"],
            "expiry": row["expiry"],
            "strike": row["strike"],
            "premium": row["premium"],
            "fair_value_gap_pct": row["fair_value_gap_pct"],
            "valuation_view": row["valuation_view"],
            "review_status": row["review_status"],
            "stock_direction": row["stock_direction"],
            "alignment_status": row["alignment_status"],
        }
        for index, (row, screened) in enumerate(zip(shortlist_rows(result), result.ranked_options), start=1)
    ]
    payload = {
        "run": {
            "generated_at": result.generated_at.isoformat(),
            "market": result.request.market,
            "analysis_mode": result.request.analysis_mode,
            "pricing_engine": result.pricing_engine,
            "review_summary": result.review_summary,
        },
        "current_option": {
            "rank": rank,
            "symbol": option.symbol,
            "company": option.company,
            "option_code": option.option_code,
            "side": option.side,
            "expiry": option.expiry,
            "days_to_expiry": option.days_to_expiry,
            "strike": option.strike,
            "premium": option.premium,
            "delta": option.delta,
            "implied_volatility": option.implied_volatility,
            "volume": option.volume,
            "open_interest": option.open_interest,
            "underlying_price": option.underlying_price,
            "model_edge_pct": option.model_edge_pct,
            "fair_value_gap_pct": option.fair_value_gap_pct,
            "valuation_view": option.valuation_view,
            "review_status": option.review_status,
            "review_flags": list(option.review_flags),
            "review_notes": option.review_notes,
            "trend_regime": option.trend_regime,
            "stock_direction": option.stock_direction,
            "stock_review_summary": option.stock_review_summary,
            "invalidation": option.invalidation,
            "alignment_status": option.alignment_status,
            "catalyst_view": option.catalyst_view,
            "stock_review_confidence": option.stock_review_confidence,
            "countertrend_risk": option.countertrend_risk,
        },
        "peer_shortlist_context": shortlist_context,
        "instructions": [
            "You are reviewing one weekly shortlisted option for human follow-up.",
            "Use research-only language and do not give trading instructions.",
            "Treat the deterministic screen and stock context as the primary evidence.",
            "If the contract looks weak, say so clearly using the review_disposition field.",
            "Keep follow_up_checks concrete and operational for a human reviewer.",
        ],
        "allowed_review_dispositions": ["follow_up", "watch", "pass"],
        "style": "Professional desk note. State evidence, interpretation, and risk.",
    }
    return json.dumps(payload, indent=2)


def build_weekly_screen_option_entries(
    result: WeeklyScreenResult,
    *,
    review_results: dict[str, WeeklyOptionAgentReviewResult],
    review_failures: dict[str, str],
    run_path: pathlib.Path,
    artifact_paths: tuple[str, ...],
    top_k: int,
) -> list[WeeklyScreenOptionEntry]:
    run_key = weekly_screen_run_key(result)
    entries: list[WeeklyScreenOptionEntry] = []
    for rank, option in select_weekly_screen_options_for_agent_review(result, top_k):
        entries.append(
            WeeklyScreenOptionEntry(
                title=f"{option.symbol} {option.side} {option.expiry} {_format_strike(option.strike)}",
                date=result.generated_at.date().isoformat(),
                run_key=run_key,
                run_path=str(run_path),
                external_id=weekly_screen_option_external_id(run_key, option.option_code),
                screened_option=option,
                rank=rank,
                review_result=review_results.get(option.option_code),
                review_error=review_failures.get(option.option_code),
                artifact_paths=artifact_paths,
            )
        )
    return entries


def build_weekly_screen_run_entry(
    result: WeeklyScreenResult,
    *,
    option_entries: list[WeeklyScreenOptionEntry],
    run_path: pathlib.Path,
    artifact_paths: tuple[str, ...],
    review_warnings: tuple[str, ...],
) -> WeeklyScreenRunEntry:
    run_key = weekly_screen_run_key(result)
    return WeeklyScreenRunEntry(
        title=f"Weekly Options Screen - {result.generated_at.date().isoformat()}",
        date=result.generated_at.date().isoformat(),
        run_key=run_key,
        run_path=str(run_path),
        external_id=weekly_screen_run_external_id(run_key),
        result=result,
        option_entries=tuple(option_entries),
        artifact_paths=artifact_paths,
        review_warnings=review_warnings,
    )


def build_weekly_screen_journal_payloads(
    result: WeeklyScreenResult,
    *,
    review_results: dict[str, WeeklyOptionAgentReviewResult],
    review_failures: dict[str, str],
    run_path: pathlib.Path,
    artifact_paths: tuple[str, ...],
    top_k: int,
) -> list[NotionEntryPayload]:
    option_entries = build_weekly_screen_option_entries(
        result,
        review_results=review_results,
        review_failures=review_failures,
        run_path=run_path,
        artifact_paths=artifact_paths,
        top_k=top_k,
    )
    run_entry = build_weekly_screen_run_entry(
        result,
        option_entries=option_entries,
        run_path=run_path,
        artifact_paths=artifact_paths,
        review_warnings=tuple(review_failures.values()),
    )
    return [
        render_weekly_screen_run_payload(run_entry),
        *(render_weekly_screen_option_payload(entry) for entry in option_entries),
    ]


def render_weekly_screen_run_payload(entry: WeeklyScreenRunEntry) -> NotionEntryPayload:
    result = entry.result
    run_summary = weekly_run_summary(result)
    report_sections = {section["title"]: section for section in screen_report_sections(result)}
    discovery_summary = report_sections["How Universe Discovery Works"]["summary"]
    safety_items = report_sections["How To Read The Output Safely"]["items"]
    discovery_rows = report_sections["How Universe Discovery Works"]["table"]
    gate_trace_rows = gate_summary_rows(result)
    gate_trace_items = report_sections["Gate Trace"]["items"]
    review_status_rows = [
        {
            "Rank": str(option_entry.rank),
            "Symbol": option_entry.screened_option.symbol,
            "Option Code": option_entry.screened_option.option_code,
            "Disposition": option_entry.review_result.review_disposition if option_entry.review_result else "Unavailable",
            "Status": option_entry.screened_option.review_status,
            "Failure": option_entry.review_error or "",
        }
        for option_entry in entry.option_entries
    ]
    shortlist_table = [
        {
            "Rank": str(index),
            "Symbol": option.symbol,
            "Side": option.side,
            "Expiry": option.expiry,
            "Strike": _format_strike(option.strike),
            "Premium": f"{option.premium:.4f}",
            "Fair Value Gap %": f"{option.fair_value_gap_pct:.1%}",
            "Valuation View": option.valuation_view,
            "Stock Direction": option.stock_direction,
            "Review Status": option.review_status,
        }
        for index, option in enumerate(result.ranked_options, start=1)
    ]
    run_stats = [
        {
            "Generated At": result.generated_at.strftime("%Y-%m-%d %H:%M:%S %Z").strip(),
            "Market": result.request.market,
            "Analysis Mode": result.request.analysis_mode,
            "Pricing Engine": result.pricing_engine,
        },
        {
            "Attempted Symbols": str(run_summary["attempted_symbols"]),
            "Successful Symbols": str(run_summary["successful_symbol_count"]),
            "Skipped Symbols": str(run_summary["skipped_symbol_count"]),
            "Shortlist Size": str(len(result.ranked_options)),
        },
        {
            "GPT-5.5 Reviews": str(len([entry for entry in entry.option_entries if entry.review_result is not None])),
            "GPT Failures": str(len([warning for warning in entry.review_warnings if warning])),
            "Reviewed Shortlist": "Yes" if result.reviewed_shortlist else "No",
            "Reviewer Model": result.reviewer_model or "",
        },
    ]
    blocks: list[dict[str, Any]] = []
    blocks.extend(_heading_block("heading_2", "Methodology Summary"))
    blocks.extend(_paragraph_blocks(report_sections["What This Run Is"]["content"]))
    blocks.extend(_paragraph_blocks(discovery_summary))
    blocks.extend(_heading_block("heading_2", "Run Stats"))
    blocks.append(_table_block_from_dict_rows(run_stats))
    blocks.extend(_heading_block("heading_2", "Discovery Stats"))
    blocks.append(_table_block_from_dict_rows(discovery_rows))
    blocks.extend(_heading_block("heading_2", "Gate Trace"))
    blocks.append(_table_block_from_dict_rows(gate_trace_rows))
    blocks.extend(_bulleted_list_blocks(str(item) for item in gate_trace_items))
    blocks.extend(_heading_block("heading_2", "Shortlist"))
    blocks.append(_table_block_from_dict_rows(shortlist_table))
    blocks.extend(_heading_block("heading_2", "GPT-5.5 Option Review Status"))
    if review_status_rows:
        blocks.append(_table_block_from_dict_rows(review_status_rows))
    else:
        blocks.extend(_paragraph_blocks("No separate GPT-5.5 option reviews ran for this screen."))
    if entry.review_warnings:
        blocks.extend(_bulleted_list_blocks(f"Review warning: {warning}" for warning in entry.review_warnings))
    blocks.extend(_heading_block("heading_2", "Artifacts"))
    blocks.extend(_bulleted_list_blocks([f"Run path: {entry.run_path}", *entry.artifact_paths]))
    blocks.extend(_heading_block("heading_2", "Safety Notes"))
    blocks.extend(_bulleted_list_blocks(str(item) for item in safety_items))
    return NotionEntryPayload(
        title=entry.title,
        date=entry.date,
        entry_type="Weekly Screen Run",
        source="naval-analyst",
        external_id=entry.external_id,
        run_key=entry.run_key,
        run_path=entry.run_path,
        blocks=tuple(blocks),
    )


def render_weekly_screen_option_payload(entry: WeeklyScreenOptionEntry) -> NotionEntryPayload:
    option = entry.screened_option
    stock_context_row = {
        "Trend Regime": option.trend_regime,
        "Stock Direction": option.stock_direction,
        "Stock Review Summary": option.stock_review_summary,
        "Invalidation": option.invalidation,
        "Alignment Status": option.alignment_status,
        "Catalyst View": option.catalyst_view,
    }
    contract_row = {
        "Option Code": option.option_code,
        "Side": option.side,
        "Expiry": option.expiry,
        "Days To Expiry": str(option.days_to_expiry),
        "Strike": _format_strike(option.strike),
        "Underlying Price": f"{option.underlying_price:.4f}",
    }
    screen_metrics_row = {
        "Premium": f"{option.premium:.4f}",
        "Delta": f"{option.delta:.4f}",
        "IV": f"{option.implied_volatility:.4f}",
        "Volume": str(option.volume),
        "Open Interest": str(option.open_interest),
        "Composite Score": f"{option.composite_score:.4f}",
    }
    valuation_row = {
        "Fair Value Gap %": f"{option.fair_value_gap_pct:.1%}",
        "Model Edge %": f"{option.model_edge_pct:.1%}",
        "Valuation View": option.valuation_view,
        "Review Status": option.review_status,
        "Review Flags": ", ".join(option.review_flags) or "none",
        "Review Notes": option.review_notes or "",
    }
    blocks: list[dict[str, Any]] = []
    blocks.extend(_heading_block("heading_2", "Stock Context"))
    blocks.append(_table_block_from_dict_rows([stock_context_row]))
    blocks.extend(_heading_block("heading_2", "Deterministic Screen Metrics"))
    blocks.append(_table_block_from_dict_rows([contract_row]))
    blocks.append(_table_block_from_dict_rows([screen_metrics_row]))
    blocks.append(_table_block_from_dict_rows([valuation_row]))
    blocks.extend(_heading_block("heading_2", "GPT-5.5 Analysis"))
    if entry.review_result is None:
        blocks.extend(_paragraph_blocks(f"No GPT-5.5 review is available for this option. {entry.review_error or ''}".strip()))
    else:
        review = entry.review_result
        blocks.append(
            _table_block_from_dict_rows(
                [
                    {
                        "Model": review.model_used,
                        "Disposition": review.review_disposition,
                        "Symbol": review.symbol,
                        "Option Code": review.option_code,
                    }
                ]
            )
        )
        blocks.extend(_paragraph_blocks(review.summary))
        blocks.extend(_paragraph_blocks(review.why_this_contract))
        blocks.extend(_heading_block("heading_3", "Main Risks"))
        blocks.extend(_bulleted_list_blocks(review.main_risks))
        blocks.extend(_heading_block("heading_3", "Invalidation"))
        blocks.extend(_paragraph_blocks(review.invalidation))
        blocks.extend(_heading_block("heading_3", "Follow-Up Checks"))
        blocks.extend(_bulleted_list_blocks(review.follow_up_checks))
    blocks.extend(_heading_block("heading_2", "Artifacts"))
    blocks.extend(_bulleted_list_blocks([f"Run path: {entry.run_path}", *entry.artifact_paths]))
    return NotionEntryPayload(
        title=entry.title,
        date=entry.date,
        entry_type="Weekly Screen Option",
        source="naval-analyst",
        external_id=entry.external_id,
        run_key=entry.run_key,
        run_path=entry.run_path,
        ticker=option.symbol,
        option_side=option.side,
        blocks=tuple(blocks),
    )


def _format_strike(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}"
