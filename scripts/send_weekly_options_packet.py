#!/usr/bin/env python3
"""Build and optionally send a weekly options packet with attached tear sheets."""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import os
import pathlib
import re
import sys
import urllib.error

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from quant_researcher_desk.moomoo_options_report import MoomooOpenDQuoteClient, OptionsReportError  # noqa: E402
from quant_researcher_desk.notion_trade_journal import (  # noqa: E402
    NotionSyncError,
    build_weekly_sync_payloads,
    create_notion_client,
    load_notion_sync_config,
    sync_payloads,
)
from quant_researcher_desk.weekly_agent_review import WeeklyAgentReviewConfig, load_weekly_agent_review_config  # noqa: E402
from quant_researcher_desk.weekly_options_packet import (  # noqa: E402
    build_weekly_options_packet,
    write_weekly_options_packet_html,
    write_weekly_options_packet_pdf,
)
from quant_researcher_desk.weekly_options_screener import (  # noqa: E402
    FixtureWeeklyScreenProvider,
    WeeklyReviewerConfig,
    WeeklyScreenRequest,
    build_weekly_options_screen,
    load_weekly_reviewer_config,
)
from quant_researcher_desk.options_research import FixtureOptionsResearchProvider  # noqa: E402
from scripts.telegram_notify import TelegramSendError, load_env, post_telegram_document  # noqa: E402


def slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9-]+", "-", value.strip()).strip("-").lower() or "report"


def render_attachment(packet, output_dir: pathlib.Path, report_format: str) -> pathlib.Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    base = output_dir / slug(packet.title)
    if report_format == "html":
        return write_weekly_options_packet_html(base.with_suffix(".html"), packet)
    return write_weekly_options_packet_pdf(base.with_suffix(".pdf"), packet)


def main() -> int:
    env = load_env(ROOT / ".env.example")
    env.update(load_env(ROOT / ".env"))
    env.update(os.environ)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--post", action="store_true")
    parser.add_argument("--fixture", action="store_true")
    parser.add_argument("--market", default="US")
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--min-days-out", type=int, default=5)
    parser.add_argument("--target-days-out", type=int, default=7)
    parser.add_argument("--min-volume", type=int, default=100)
    parser.add_argument("--min-open-interest", type=int, default=100)
    parser.add_argument("--min-abs-delta", type=float, default=0.20)
    parser.add_argument("--max-abs-delta", type=float, default=0.60)
    parser.add_argument("--historical-volatility", type=float, default=0.25)
    parser.add_argument("--max-underlyings", type=int, default=250)
    parser.add_argument("--output-dir", type=pathlib.Path, default=ROOT / "reports" / "weekly-options-packets")
    parser.add_argument("--report-format", choices=("pdf", "html"), default="pdf")
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
    agent_review_defaults = load_weekly_agent_review_config(env)
    parser.add_argument("--agent-review", action="store_true", default=agent_review_defaults.enabled)
    parser.add_argument("--agent-review-model", default=agent_review_defaults.model)
    parser.add_argument("--agent-review-fallback-model", default=agent_review_defaults.fallback_model)
    parser.add_argument("--agent-review-timeout-seconds", type=int, default=agent_review_defaults.timeout_seconds)
    parser.add_argument("--agent-review-max-tokens", type=int, default=agent_review_defaults.max_tokens)
    parser.add_argument("--agent-review-temperature", type=float, default=agent_review_defaults.temperature)
    parser.add_argument("--notion-sync", action="store_true")
    parser.add_argument("--notion-dry-run", action="store_true")
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
    agent_review_config = WeeklyAgentReviewConfig(
        enabled=args.agent_review,
        provider=agent_review_defaults.provider,
        base_url=agent_review_defaults.base_url,
        model=args.agent_review_model,
        fallback_model=args.agent_review_fallback_model,
        timeout_seconds=args.agent_review_timeout_seconds,
        max_tokens=args.agent_review_max_tokens,
        temperature=args.agent_review_temperature,
        api_key=agent_review_defaults.api_key,
    )

    current = dt.datetime.now(dt.timezone.utc).astimezone()
    try:
        if args.fixture:
            weekly_provider = FixtureWeeklyScreenProvider(anchor_date=current.date())
            options_provider = FixtureOptionsResearchProvider(anchor_date=current.date())
            weekly_result = build_weekly_options_screen(weekly_provider, request, now=current, reviewer_config=reviewer_config)
            packet = build_weekly_options_packet(
                weekly_result,
                options_provider,
                now=current,
                agent_review_config=agent_review_config,
            )
        else:
            with MoomooOpenDQuoteClient(host=args.opend_host, port=args.opend_port) as provider:
                weekly_result = build_weekly_options_screen(provider, request, now=current, reviewer_config=reviewer_config)
                packet = build_weekly_options_packet(
                    weekly_result,
                    provider,
                    now=current,
                    agent_review_config=agent_review_config,
                )
    except (OptionsReportError, OSError) as exc:
        print(f"weekly options packet failed: {exc}", file=sys.stderr)
        return 1

    attachment = render_attachment(packet, args.output_dir, args.report_format)
    notion_config = load_notion_sync_config(env)
    notion_enabled = args.notion_sync or args.notion_dry_run or notion_config.enabled
    notion_config = dataclasses.replace(notion_config, enabled=notion_enabled, dry_run=(args.notion_dry_run or notion_config.dry_run))
    if notion_enabled:
        try:
            notion_results = sync_payloads(
                create_notion_client(notion_config),
                notion_config,
                build_weekly_sync_payloads(packet, run_path=args.output_dir, attachment_path=attachment),
            )
        except NotionSyncError as exc:
            print(f"notion sync failed: {exc}", file=sys.stderr)
            return 1
        for result in notion_results:
            print(f"notion: {result.action}: {result.title}")
    caption = (
        f"<b>{packet.title}</b>\n"
        f"Generated: <code>{packet.generated_at.strftime('%Y-%m-%d %H:%M %Z').strip()}</code>\n"
        f"Shortlist: <code>{len(packet.weekly_result.ranked_options)}</code>\n"
        "Overview first, detailed tear sheets attached."
    )
    if args.dry_run or not args.post:
        print(packet.title)
        print(caption)
        print(f"attachment: {attachment}")
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
