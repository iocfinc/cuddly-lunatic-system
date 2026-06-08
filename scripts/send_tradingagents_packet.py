#!/usr/bin/env python3
"""Build and optionally send a TradingAgents-backed research decision packet."""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
import urllib.error

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from quant_researcher_desk.execution_recovery import SymbolExecutionError  # noqa: E402
from quant_researcher_desk.moomoo_options_report import MoomooOpenDQuoteClient  # noqa: E402
from quant_researcher_desk.options_research import OptionsResearchRequest  # noqa: E402
from quant_researcher_desk.reporting import ReportRenderError, render_pdf_report, write_html_report  # noqa: E402
from quant_researcher_desk.tradingagents_packet import (  # noqa: E402
    TradingAgentsPacketRequest,
    build_decision_packet,
    build_desk_evidence_pack,
    decision_packet_sections,
    format_decision_packet_telegram_html,
    load_tradingagents_config,
    persist_decision_packet,
    run_tradingagents_debate_for_symbol,
)
from scripts.telegram_notify import TelegramSendError, load_env, post_telegram_document  # noqa: E402


def render_attachment(
    title: str,
    sections: list[dict[str, object]],
    metadata: dict[str, object],
    output_dir: pathlib.Path,
    report_format: str,
) -> pathlib.Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    base = output_dir / title.lower().replace(" ", "-").replace(".", "")
    if report_format == "html":
        return write_html_report(title, sections, metadata, base.with_suffix(".html"))
    try:
        return render_pdf_report(title, sections, metadata, base.with_suffix(".pdf"))
    except ReportRenderError as exc:
        print(f"report PDF fallback: {exc}", file=sys.stderr)
        return write_html_report(title, sections, metadata, base.with_suffix(".html"))


def main() -> int:
    env = load_env(ROOT / ".env.example")
    env.update(load_env(ROOT / ".env"))
    os.environ.update({key: value for key, value in env.items() if value})

    parser = argparse.ArgumentParser(description="Build a TradingAgents-backed research decision packet.")
    parser.add_argument("--dry-run", action="store_true", help="Print the caption, attachment path, and artifact path without posting.")
    parser.add_argument("--post", action="store_true", help="Post the packet attachment when Telegram is enabled.")
    parser.add_argument("--fixture", action="store_true", help="Use deterministic local packet synthesis without live LLM or TradingAgents.")
    parser.add_argument("--symbol", default=env.get("MOOMOO_DEFAULT_SYMBOL", "US.TSM"))
    parser.add_argument("--analysis-date", help="Analysis date in YYYY-MM-DD format for the live TradingAgents adapter.")
    parser.add_argument("--option-code")
    parser.add_argument("--option-type", choices=("CALL", "PUT"), default="CALL")
    parser.add_argument("--strike", type=float)
    parser.add_argument("--expiry")
    parser.add_argument("--historical-volatility", type=float, default=0.35)
    parser.add_argument("--risk-free-rate", type=float, default=0.04)
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

    request = OptionsResearchRequest(
        symbol=args.symbol,
        option_code=args.option_code,
        option_type=args.option_type,
        strike=args.strike,
        expiry=args.expiry,
        historical_volatility=args.historical_volatility,
        risk_free_rate=args.risk_free_rate,
    )
    packet_request = TradingAgentsPacketRequest(
        symbol=args.symbol,
        analysis_date=args.analysis_date,
        report_format=args.report_format,
        post_to_telegram=args.post,
    )

    if not args.fixture and not config.enabled:
        print(
            "tradingagents packet failed: TradingAgents is disabled. Set TRADINGAGENTS_ENABLED=true to enable the optional adapter.",
            file=sys.stderr,
        )
        return 1

    try:
        if args.fixture:
            from quant_researcher_desk.options_research import FixtureOptionsResearchProvider  # noqa: E402

            evidence_pack = build_desk_evidence_pack(FixtureOptionsResearchProvider(), request)
        else:
            with MoomooOpenDQuoteClient(host=args.opend_host, port=args.opend_port) as provider:
                evidence_pack = build_desk_evidence_pack(provider, request)
    except SymbolExecutionError as exc:
        print(f"tradingagents packet failed: {exc.single_symbol_message()}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"tradingagents packet failed: {exc}", file=sys.stderr)
        return 1

    try:
        debate = run_tradingagents_debate_for_symbol(config, packet_request, evidence_pack, fixture=args.fixture)
    except SymbolExecutionError as exc:
        print(f"tradingagents packet failed: {exc.single_symbol_message()}", file=sys.stderr)
        return 1

    packet = build_decision_packet(
        packet_request,
        evidence_pack,
        debate,
        source_ref="fixture" if args.fixture else config.ref,
    )
    sections = decision_packet_sections(packet)
    metadata = {
        "generated_at": packet.generated_at.strftime("%Y-%m-%d %H:%M:%S %Z").strip(),
        "symbol": packet.symbol,
        "label": packet.label,
        "source_ref": packet.source_ref,
    }
    attachment = render_attachment(packet.title, sections, metadata, args.output_dir, args.report_format)
    artifact = persist_decision_packet(packet, config.results_dir)
    caption = format_decision_packet_telegram_html(packet)

    if args.dry_run or not args.post:
        print(caption)
        print(f"attachment: {attachment}")
        print(f"artifact: {artifact}")
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
        post_telegram_document(token, chat_id, attachment, caption=caption, parse_mode="HTML")
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
