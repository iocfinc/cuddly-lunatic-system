#!/usr/bin/env python3
"""Send a near-expiry TSMC options report from local Moomoo OpenD to Telegram."""

from __future__ import annotations

import argparse
import pathlib
import sys
import urllib.error

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from quant_researcher_desk.moomoo_options_report import (  # noqa: E402
    MoomooOpenDQuoteClient,
    OptionsReportError,
    build_options_report,
    format_telegram_html,
)
from scripts.telegram_notify import (  # noqa: E402
    TelegramSendError,
    load_env,
    post_telegram,
)


def main() -> int:
    env = load_env(ROOT / ".env.example")
    env.update(load_env(ROOT / ".env"))

    parser = argparse.ArgumentParser(description="Build and optionally send a Moomoo OpenD TSMC options report.")
    parser.add_argument("--dry-run", action="store_true", help="Print the Telegram HTML without posting.")
    parser.add_argument("--post", action="store_true", help="Post to Telegram when TELEGRAM_NOTIFY_ENABLED=true.")
    parser.add_argument("--symbol", default=env.get("MOOMOO_DEFAULT_SYMBOL", "US.TSM"))
    parser.add_argument("--expiry", default=None, help="Expiry date in YYYY-MM-DD format. Defaults to nearest future expiry.")
    parser.add_argument("--rows", type=int, default=5, help="Number of calls and puts to include.")
    parser.add_argument("--opend-host", default=env.get("MOOMOO_OPEND_HOST", "127.0.0.1"))
    parser.add_argument("--opend-port", type=int, default=int(env.get("MOOMOO_OPEND_PORT", "11111")))
    args = parser.parse_args()

    try:
        with MoomooOpenDQuoteClient(host=args.opend_host, port=args.opend_port) as client:
            report = build_options_report(client, symbol=args.symbol, expiry=args.expiry, rows=args.rows)
    except OptionsReportError as exc:
        print(f"moomoo options report failed: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"moomoo options report failed: cannot connect to OpenD at {args.opend_host}:{args.opend_port}: {exc}", file=sys.stderr)
        return 1

    message = format_telegram_html(report)
    if args.dry_run or not args.post:
        print(message)
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
        post_telegram(token, chat_id, message, parse_mode="HTML")
    except TelegramSendError as exc:
        print(f"telegram notification failed: {exc}", file=sys.stderr)
        return 1
    except (TimeoutError, urllib.error.URLError) as exc:
        print(f"telegram notification failed: {exc}", file=sys.stderr)
        return 1
    print("telegram notification sent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
