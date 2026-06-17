#!/usr/bin/env python3
"""Build and optionally send a TradingAgents-backed watchlist digest."""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import pathlib
import sys
import urllib.error

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from quant_researcher_desk.execution_recovery import SymbolExecutionError  # noqa: E402
from quant_researcher_desk.moomoo_options_report import MoomooOpenDQuoteClient, OptionsReportError  # noqa: E402
from quant_researcher_desk.options_research import FixtureOptionsResearchProvider, OptionsResearchRequest  # noqa: E402
from quant_researcher_desk.reporting import ReportRenderError, render_pdf_report, write_html_report  # noqa: E402
from quant_researcher_desk.tradingagents_packet import (  # noqa: E402
    TradingAgentsPacketRequest,
    build_decision_packet,
    build_desk_evidence_pack,
    load_tradingagents_config,
    run_tradingagents_debate_for_symbol,
)
from quant_researcher_desk.tradingagents_watchlist import (  # noqa: E402
    WatchlistDigestError,
    WatchlistSymbolStatus,
    build_watchlist_digest_from_packets,
    build_watchlist_securities,
)
from scripts.telegram_notify import TelegramSendError, load_env, post_telegram_document  # noqa: E402


def render_attachment(title: str, sections: list[dict[str, object]], metadata: dict[str, object], output_dir: pathlib.Path, report_format: str) -> pathlib.Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    base = output_dir / title.lower().replace(" ", "-")
    if report_format == "html":
        return write_html_report(title, sections, metadata, base.with_suffix(".html"))


def write_digest_summary(
    output_dir: pathlib.Path,
    digest_title: str,
    metadata: dict[str, object],
    statuses: list[WatchlistSymbolStatus],
) -> pathlib.Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    base = output_dir / digest_title.lower().replace(" ", "-")
    summary_path = base.with_name(f"{base.name}-summary.json")
    payload = {
        "digest_title": digest_title,
        "metadata": metadata,
        "symbol_statuses": [dataclasses.asdict(status) for status in statuses],
        "published_partial_output": bool(metadata.get("succeeded")) and int(metadata.get("succeeded", 0)) < int(metadata.get("attempted", 0)),
    }
    summary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return summary_path
    try:
        return render_pdf_report(title, sections, metadata, base.with_suffix(".pdf"))
    except ReportRenderError as exc:
        print(f"report PDF fallback: {exc}", file=sys.stderr)
        return write_html_report(title, sections, metadata, base.with_suffix(".html"))


def parse_symbols(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [symbol.strip() for symbol in raw.split(",") if symbol.strip()]


def collect_watchlist_symbols(provider: MoomooOpenDQuoteClient, group_name: str | None, max_candidates: int) -> list[str]:
    groups = provider.get_user_security_groups()
    filtered_groups = [
        group for group in groups
        if str(group.get("group_name", "")).strip()
        and (group_name is None or str(group.get("group_name", "")).strip() == group_name)
    ]
    rows_by_group: dict[str, list[dict[str, object]]] = {}
    collected: list[str] = []
    for group in filtered_groups:
        current_group_name = str(group.get("group_name", "")).strip()
        rows_by_group[current_group_name] = provider.get_user_security(current_group_name)
        securities = build_watchlist_securities(
            filtered_groups,
            rows_by_group,
            group_name=group_name,
            max_candidates=max_candidates,
        )
        collected = [security.symbol for security in securities]
        if len(collected) >= max_candidates:
            return collected
    if collected:
        return collected
    securities = build_watchlist_securities(filtered_groups, rows_by_group, group_name=group_name, max_candidates=max_candidates)
    return [security.symbol for security in securities]


def main() -> int:
    env = load_env(ROOT / ".env.example")
    env.update(load_env(ROOT / ".env"))
    os.environ.update({key: value for key, value in env.items() if value})

    parser = argparse.ArgumentParser(description="Build a TradingAgents-backed watchlist digest.")
    parser.add_argument("--dry-run", action="store_true", help="Print the caption and attachment path without posting.")
    parser.add_argument("--post", action="store_true", help="Post the digest attachment when Telegram is enabled.")
    parser.add_argument("--fixture", action="store_true", help="Use deterministic local packet synthesis without OpenD or a live LLM.")
    parser.add_argument("--symbols", help="Comma-separated symbols to analyze instead of reading the OpenD watchlist.")
    parser.add_argument("--group-name", help="Optional OpenD watchlist group to limit the scan to.")
    parser.add_argument("--analysis-date", help="Analysis date in YYYY-MM-DD format for the live TradingAgents adapter.")
    parser.add_argument("--max-candidates", type=int, default=5)
    parser.add_argument("--top-n", type=int, default=3)
    parser.add_argument("--output-dir", type=pathlib.Path, default=ROOT / "reports" / "tradingagents")
    parser.add_argument("--results-dir", type=pathlib.Path, help="Override the repo-local decision packet artifact directory.")
    parser.add_argument("--report-format", choices=("pdf", "html"), default="pdf")
    parser.add_argument("--opend-host", default=env.get("MOOMOO_OPEND_HOST", "127.0.0.1"))
    parser.add_argument("--opend-port", type=int, default=int(env.get("MOOMOO_OPEND_PORT", "11111")))
    args = parser.parse_args()

    config_env = dict(env)
    if args.results_dir:
        config_env["TRADINGAGENTS_RESULTS_DIR"] = str(args.results_dir)
    config = load_tradingagents_config(ROOT, env=env, runtime_env=config_env)

    symbols = parse_symbols(args.symbols)
    if args.fixture and not symbols:
        symbols = ["US.NVDA", "US.TSM", "US.META"]

    if not args.fixture and not config.enabled:
        print(
            "tradingagents watchlist digest failed: TradingAgents is disabled. Set TRADINGAGENTS_ENABLED=true to enable the optional adapter.",
            file=sys.stderr,
        )
        return 1

    try:
        if not symbols:
            with MoomooOpenDQuoteClient(host=args.opend_host, port=args.opend_port) as provider:
                symbols = collect_watchlist_symbols(provider, args.group_name, args.max_candidates)

        packets = []
        statuses: list[WatchlistSymbolStatus] = []
        if args.fixture:
            provider = FixtureOptionsResearchProvider()
            for symbol in symbols[: args.max_candidates]:
                packet_request = TradingAgentsPacketRequest(
                    symbol=symbol,
                    analysis_date=args.analysis_date,
                    report_format=args.report_format,
                    post_to_telegram=args.post,
                )
                try:
                    evidence_pack = build_desk_evidence_pack(provider, OptionsResearchRequest(symbol=symbol))
                    debate = run_tradingagents_debate_for_symbol(
                        config,
                        packet_request,
                        evidence_pack,
                        fixture=True,
                    )
                except SymbolExecutionError as exc:
                    statuses.append(
                        WatchlistSymbolStatus(
                            symbol=symbol,
                            status=exc.skip.bucket,
                            reason_code=exc.reason_code,
                            detail=exc.detail,
                        )
                    )
                    print(f"watchlist symbol skipped: {symbol}: {exc.detail}", file=sys.stderr)
                    continue
                packet = build_decision_packet(packet_request, evidence_pack, debate, source_ref="fixture")
                packets.append(packet)
                statuses.append(WatchlistSymbolStatus(symbol=symbol, status="success", label=packet.label))
        else:
            with MoomooOpenDQuoteClient(host=args.opend_host, port=args.opend_port) as provider:
                for symbol in symbols[: args.max_candidates]:
                    packet_request = TradingAgentsPacketRequest(
                        symbol=symbol,
                        analysis_date=args.analysis_date,
                        report_format=args.report_format,
                        post_to_telegram=args.post,
                    )
                    try:
                        evidence_pack = build_desk_evidence_pack(provider, OptionsResearchRequest(symbol=symbol))
                        debate = run_tradingagents_debate_for_symbol(config, packet_request, evidence_pack, fixture=False)
                    except SymbolExecutionError as exc:
                        statuses.append(
                            WatchlistSymbolStatus(
                                symbol=symbol,
                                status=exc.skip.bucket,
                                reason_code=exc.reason_code,
                                detail=exc.detail,
                            )
                        )
                        print(f"watchlist symbol skipped: {symbol}: {exc.detail}", file=sys.stderr)
                        continue
                    packet = build_decision_packet(packet_request, evidence_pack, debate, source_ref=config.ref)
                    packets.append(packet)
                    statuses.append(WatchlistSymbolStatus(symbol=symbol, status="success", label=packet.label))
    except (OptionsReportError, WatchlistDigestError, OSError) as exc:
        print(f"tradingagents watchlist digest failed: {exc}", file=sys.stderr)
        return 1

    if not packets:
        status_counts: dict[str, int] = {}
        for status in statuses:
            status_counts[status.status] = status_counts.get(status.status, 0) + 1
        summary = ", ".join(f"{key}={value}" for key, value in sorted(status_counts.items())) or "none"
        print(
            "tradingagents watchlist digest failed: "
            "No watchlist packets survived evidence and debate generation. "
            f"attempted={len(statuses)}; skips={summary}.",
            file=sys.stderr,
        )
        return 1

    digest = build_watchlist_digest_from_packets(packets, top_n=args.top_n, symbol_statuses=statuses)
    attachment = render_attachment(digest.title, digest.sections, digest.metadata, args.output_dir, args.report_format)
    summary_path = write_digest_summary(args.output_dir, digest.title, digest.metadata, statuses)

    if args.dry_run or not args.post:
        print(digest.caption)
        print(f"attachment: {attachment}")
        print(f"summary: {summary_path}")
        return 0

    if env.get("TELEGRAM_NOTIFY_ENABLED", "false").lower() != "true":
        print("telegram notification skipped: TELEGRAM_NOTIFY_ENABLED is not true")
        return 0
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "")
    if not token or token.startswith("replace-with-") or not chat_id or chat_id.startswith("replace-with-"):
        print("telegram notification skipped: Telegram credentials are not configured", file=sys.stderr)
        return 1

    try:
        post_telegram_document(token, chat_id, attachment, caption=digest.caption, parse_mode="HTML")
    except TelegramSendError as exc:
        print(f"telegram notification failed: {exc}", file=sys.stderr)
        return 1
    except (TimeoutError, urllib.error.URLError) as exc:
        print(f"telegram notification failed: {exc}", file=sys.stderr)
        return 1
    print("telegram report sent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
