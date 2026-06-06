#!/usr/bin/env python3
"""Sync TradingAgents markdown reports into the Notion Trade Journal database."""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from quant_researcher_desk.notion_trade_journal import (  # noqa: E402
    NotionSyncError,
    build_tradingagents_entry_from_report,
    create_notion_client,
    discover_tradingagents_reports,
    load_notion_sync_config,
    lookup_stock_name_via_market_snapshot,
    render_tradingagents_payload,
    sync_payloads,
)
from scripts.telegram_notify import load_env  # noqa: E402


def _parse_since(value: str | None) -> dt.datetime | dt.date | None:
    if not value:
        return None
    text = value.strip()
    try:
        return dt.datetime.fromisoformat(text)
    except ValueError:
        return dt.date.fromisoformat(text)


def main() -> int:
    env = load_env(ROOT / ".env.example")
    env.update(load_env(ROOT / ".env"))
    env.update(os.environ)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reports-root",
        type=pathlib.Path,
        default=ROOT.parent / "TradingAgents" / "reports",
        help="Root containing */complete_report.md TradingAgents outputs.",
    )
    parser.add_argument("--since", help="Only sync reports on or after this date/time (YYYY-MM-DD or ISO datetime).")
    parser.add_argument("--limit", type=int, help="Maximum number of reports to scan.")
    parser.add_argument("--dry-run", action="store_true", help="Preview pages without writing to Notion.")
    parser.add_argument("--upsert", action="store_true", help="Force Notion writes even when NOTION_SYNC_ENABLED is false.")
    args = parser.parse_args()

    notion_config = load_notion_sync_config(env)
    notion_enabled = args.upsert or args.dry_run or notion_config.enabled
    notion_config = dataclasses.replace(
        notion_config,
        enabled=notion_enabled,
        dry_run=(args.dry_run or notion_config.dry_run) and not args.upsert,
    )
    if not notion_enabled:
        print(
            "notion sync is disabled: pass --dry-run or --upsert, or set NOTION_SYNC_ENABLED=true.",
            file=sys.stderr,
        )
        return 1

    reports_root = args.reports_root.expanduser()
    if not reports_root.exists():
        print(f"reports root not found: {reports_root}", file=sys.stderr)
        return 1

    report_paths = discover_tradingagents_reports(
        reports_root,
        since=_parse_since(args.since),
        limit=args.limit,
    )
    if not report_paths:
        print("no TradingAgents reports matched the current filters")
        return 0

    payloads = []
    skipped = 0
    for path in report_paths:
        try:
            entry = build_tradingagents_entry_from_report(
                path,
                name_lookup=lambda ticker: lookup_stock_name_via_market_snapshot(
                    ticker,
                    host=notion_config.opend_host,
                    port=notion_config.opend_port,
                ),
            )
        except Exception as exc:
            skipped += 1
            print(f"skipped: {path}: {exc}", file=sys.stderr)
            continue
        if entry.stock_name == entry.ticker:
            print(f"warning: falling back to ticker-only title for {entry.ticker}", file=sys.stderr)
        payloads.append(render_tradingagents_payload(entry))

    if not payloads:
        print("no TradingAgents reports were renderable after filtering", file=sys.stderr)
        return 1

    try:
        results = sync_payloads(create_notion_client(notion_config), notion_config, payloads)
    except NotionSyncError as exc:
        print(f"notion sync failed: {exc}", file=sys.stderr)
        return 1

    for result in results:
        print(f"{result.action}: {result.title} ({result.external_id})")
    print(f"reports processed: {len(results)}")
    if skipped:
        print(f"reports skipped: {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
