#!/usr/bin/env python3
"""Build a weekly US options shortlist from fixture data or Moomoo OpenD."""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import os
import pathlib
import sys
import urllib.error

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from quant_researcher_desk.moomoo_options_report import MoomooOpenDQuoteClient, OptionsReportError  # noqa: E402
from quant_researcher_desk.notion_trade_journal import (  # noqa: E402
    NotionSyncError,
    create_notion_client,
    load_notion_sync_config,
    sync_payloads,
)
from quant_researcher_desk.weekly_screen_journal import (  # noqa: E402
    WeeklyScreenJournalSyncConfig,
    build_weekly_screen_journal_payloads,
    load_weekly_option_agent_review_config,
    request_weekly_option_reviews,
)
from quant_researcher_desk.weekly_options_screener import (  # noqa: E402
    FixtureWeeklyScreenProvider,
    WeeklyReviewerConfig,
    WeeklyScreenRequest,
    build_weekly_options_screen,
    load_weekly_reviewer_config,
    weekly_run_summary,
    write_shortlist_csv,
    write_shortlist_html,
    write_shortlist_json,
    write_shortlist_pdf,
)
from scripts.telegram_notify import TelegramSendError, load_env, post_telegram_document  # noqa: E402


def format_weekly_screen_telegram_html(result) -> str:
    summary = weekly_run_summary(result)
    return (
        f"<b>{result.request.market} Weekly Options Screen</b>\n"
        f"Generated: <code>{result.generated_at.strftime('%Y-%m-%d %H:%M %Z').strip()}</code>\n"
        f"Shortlist: <code>{len(result.ranked_options)}</code>\n"
        f"Weekly expiry survivors: <code>{result.discovery_stats.get('with_target_expiry', 0)}</code>\n"
        f"Skipped symbols: <code>{summary['skipped_symbol_count']}</code>\n"
        "HTML explainer rendered locally; PDF attachment is included for Telegram review."
    )


def main() -> int:
    env = load_env(ROOT / ".env.example")
    env.update(load_env(ROOT / ".env"))
    env.update(os.environ)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--post", action="store_true")
    parser.add_argument("--fixture", action="store_true", help="Use deterministic local fixture data instead of OpenD.")
    parser.add_argument("--market", default="US")
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--min-days-out", type=int, default=5)
    parser.add_argument("--target-days-out", type=int, default=7)
    parser.add_argument("--min-volume", type=int, default=100)
    parser.add_argument("--min-open-interest", type=int, default=100)
    parser.add_argument("--min-abs-delta", type=float, default=0.20)
    parser.add_argument("--max-abs-delta", type=float, default=0.60)
    parser.add_argument("--historical-volatility", type=float, default=0.25)
    parser.add_argument("--max-underlyings", type=int, default=int(env.get("WEEKLY_MAX_UNDERLYINGS", "60")))
    parser.add_argument("--output-dir", type=pathlib.Path, default=ROOT / "reports" / "weekly-options")
    parser.add_argument("--report-format", choices=("html", "pdf"), default="html")
    parser.add_argument("--pricing-engine", choices=("legacy", "quantlib"), default="legacy")
    parser.add_argument("--shadow-compare", action="store_true")
    parser.add_argument("--review-shortlist", action="store_true")
    parser.add_argument("--reviewer-model", default=env.get("WEEKLY_SHORTLIST_REVIEWER_MODEL") or None)
    parser.add_argument("--analysis-mode", choices=("stock-first", "options-first"), default=env.get("WEEKLY_ANALYSIS_MODE", "stock-first"))
    parser.add_argument(
        "--stock-review",
        action=argparse.BooleanOptionalAction,
        default=env.get("WEEKLY_STOCK_REVIEW_ENABLED", "true").lower() == "true",
    )
    parser.add_argument("--stock-review-model", default=env.get("WEEKLY_STOCK_REVIEW_MODEL", "gpt-5.5"))
    parser.add_argument("--notion-sync", action="store_true")
    parser.add_argument("--notion-dry-run", action="store_true")
    parser.add_argument("--option-agent-review", action="store_true")
    parser.add_argument("--option-agent-review-model", default=env.get("WEEKLY_OPTION_AGENT_REVIEW_MODEL", "gpt-5.5"))
    parser.add_argument("--option-agent-top-k", type=int, default=int(env.get("WEEKLY_OPTION_AGENT_REVIEW_TOP_K", "5")))
    parser.add_argument(
        "--option-agent-concurrency",
        type=int,
        default=int(env.get("WEEKLY_OPTION_AGENT_REVIEW_CONCURRENCY", "3")),
    )
    parser.add_argument("--opend-host", default=env.get("MOOMOO_OPEND_HOST", "127.0.0.1"))
    parser.add_argument("--opend-port", type=int, default=int(env.get("MOOMOO_OPEND_PORT", "11111")))
    args = parser.parse_args()

    request = WeeklyScreenRequest(
        market=args.market,
        top_n=args.top_n,
        minimum_days_out=args.min_days_out,
        target_days_out=args.target_days_out,
        min_volume=args.min_volume,
        min_open_interest=args.min_open_interest,
        min_abs_delta=args.min_abs_delta,
        max_abs_delta=args.max_abs_delta,
        historical_volatility=args.historical_volatility,
        max_underlyings=args.max_underlyings,
        pricing_engine=args.pricing_engine,
        shadow_compare=args.shadow_compare,
        review_shortlist=args.review_shortlist,
        analysis_mode=args.analysis_mode,
        stock_review=args.stock_review,
        stock_review_model=args.stock_review_model,
    )
    reviewer_defaults = load_weekly_reviewer_config(env)
    reviewer_config = WeeklyReviewerConfig(
        enabled=args.review_shortlist,
        reviewer_model=args.reviewer_model,
        reviewer_profile=reviewer_defaults.reviewer_profile,
    )

    try:
        if args.fixture:
            result = build_weekly_options_screen(
                FixtureWeeklyScreenProvider(anchor_date=dt.datetime.now(dt.timezone.utc).astimezone().date()),
                request,
                reviewer_config=reviewer_config,
            )
        else:
            with MoomooOpenDQuoteClient(host=args.opend_host, port=args.opend_port) as client:
                result = build_weekly_options_screen(client, request, reviewer_config=reviewer_config)
    except (OptionsReportError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    timestamp = result.generated_at.strftime("%Y%m%d-%H%M%S")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = write_shortlist_csv(args.output_dir / f"{timestamp}-weekly-shortlist.csv", result)
    json_path = write_shortlist_json(args.output_dir / f"{timestamp}-weekly-shortlist.json", result)
    html_path = write_shortlist_html(args.output_dir / f"{timestamp}-weekly-shortlist.html", result)

    print(f"{result.request.market} Weekly Options Screen")
    print(f"csv: {csv_path}")
    print(f"json: {json_path}")
    print(f"html: {html_path}")
    summary = weekly_run_summary(result)
    print(f"attempted-symbols: {summary['attempted_symbols']}")
    print(f"successful-symbols: {summary['successful_symbol_count']}")
    print(f"skipped-symbols: {summary['skipped_symbol_count']}")
    for gate_row in result.gate_summary.stage_rows:
        print(f"gate-stage: {gate_row.stage}: passed={gate_row.passed} failed={gate_row.failed}")
    print(f"pricing-engine: {result.pricing_engine}")
    print(f"analysis-mode: {result.request.analysis_mode}")
    print(f"stock-review: {'yes' if result.request.stock_review else 'no'}")
    print(f"shadow-compare: {'yes' if result.shadow_compare else 'no'}")
    if result.reviewed_shortlist:
        print(f"reviewed-shortlist: yes")
    pdf_path: pathlib.Path | None = None
    if args.report_format == "pdf" or args.dry_run or args.post:
        pdf_path = write_shortlist_pdf(args.output_dir / f"{timestamp}-weekly-shortlist.pdf", result)
        print(f"pdf: {pdf_path}")

    notion_config = load_notion_sync_config(env)
    notion_enabled = args.notion_sync or args.notion_dry_run or notion_config.enabled
    notion_config = dataclasses.replace(
        notion_config,
        enabled=notion_enabled,
        dry_run=(args.notion_dry_run or notion_config.dry_run),
    )
    option_agent_review_config = load_weekly_option_agent_review_config(env)
    option_agent_review_enabled = args.option_agent_review or option_agent_review_config.enabled
    option_agent_review_config = dataclasses.replace(
        option_agent_review_config,
        enabled=option_agent_review_enabled,
        model=args.option_agent_review_model,
        top_k=max(1, args.option_agent_top_k),
        concurrency=max(1, args.option_agent_concurrency),
    )
    journal_sync_config = WeeklyScreenJournalSyncConfig(
        notion_enabled=notion_config.enabled,
        notion_dry_run=notion_config.dry_run,
        option_agent_review=option_agent_review_config,
    )
    option_review_results: dict[str, object] = {}
    option_review_failures: dict[str, str] = {}
    if journal_sync_config.option_agent_review.enabled:
        option_review_results, option_review_failures = request_weekly_option_reviews(
            result,
            journal_sync_config.option_agent_review,
        )
        print(f"option-agent-reviewed: {len(option_review_results)}")
        print(f"option-agent-failures: {len(option_review_failures)}")
        if option_review_failures:
            for option_code, message in sorted(option_review_failures.items()):
                print(f"option-agent-warning: {option_code}: {message}")
    if journal_sync_config.notion_enabled:
        artifact_paths = tuple(
            f"{label}: {path}"
            for label, path in (
                ("csv", csv_path),
                ("json", json_path),
                ("html", html_path),
                ("pdf", pdf_path),
            )
            if path is not None
        )
        try:
            notion_results = sync_payloads(
                create_notion_client(notion_config),
                notion_config,
                build_weekly_screen_journal_payloads(
                    result,
                    review_results=option_review_results,
                    review_failures=option_review_failures,
                    run_path=args.output_dir,
                    artifact_paths=artifact_paths,
                    top_k=journal_sync_config.option_agent_review.top_k,
                ),
            )
        except NotionSyncError as exc:
            print(f"notion sync failed: {exc}", file=sys.stderr)
            return 1
        for sync_result in notion_results:
            print(f"notion: {sync_result.action}: {sync_result.title}")

    if args.dry_run:
        attachment = pdf_path or html_path
        print(format_weekly_screen_telegram_html(result))
        print(f"attachment: {attachment}")
        return 0
    if not args.post:
        return 0

    if env.get("TELEGRAM_NOTIFY_ENABLED", "false").lower() != "true":
        print("telegram notification skipped: TELEGRAM_NOTIFY_ENABLED is not true")
        return 0
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "")
    if not token or token.startswith("replace-with-") or not chat_id or chat_id.startswith("replace-with-"):
        print("telegram notification skipped: Telegram credentials are not configured", file=sys.stderr)
        return 1

    attachment = pdf_path or write_shortlist_pdf(args.output_dir / f"{timestamp}-weekly-shortlist.pdf", result)
    caption = format_weekly_screen_telegram_html(result)
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
