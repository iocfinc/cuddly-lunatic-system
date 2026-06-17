#!/usr/bin/env python3
"""Send one catalyst-driven options screen report to Telegram."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import shlex
import sys
import urllib.error

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from quant_researcher_desk.catalyst_options_screen import (  # noqa: E402
    DEFAULT_CANDIDATES,
    FixtureCatalystOptionsProvider,
    build_catalyst_options_screen,
    catalyst_report_sections,
    format_catalyst_telegram_html,
)
from quant_researcher_desk.moomoo_options_report import MoomooOpenDQuoteClient  # noqa: E402
from quant_researcher_desk.reporting import render_pdf_report  # noqa: E402
from scripts.telegram_notify import TelegramSendError, load_env, post_telegram_document  # noqa: E402


def write_run_ledger(
    ledger_path: pathlib.Path,
    *,
    status: str,
    mode: str,
    output_dir: pathlib.Path,
    artifact_path: pathlib.Path | None,
    blocker: str | None,
) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": status,
        "mode": mode,
        "command_shape": " ".join(shlex.quote(part) for part in sys.argv),
        "argv": sys.argv,
        "output_dir": str(output_dir),
        "artifact_path": str(artifact_path) if artifact_path is not None else None,
        "blocker": blocker,
    }
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(f"{json.dumps(entry, sort_keys=True)}\n")


def main() -> int:
    env = load_env(ROOT / ".env.example")
    env.update(load_env(ROOT / ".env"))

    parser = argparse.ArgumentParser(description="Build and send a catalyst options screen.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--post", action="store_true")
    parser.add_argument("--output-dir", type=pathlib.Path, default=ROOT / "reports" / "catalyst-options")
    parser.add_argument("--run-ledger", type=pathlib.Path, default=None)
    parser.add_argument("--fixture", action="store_true")
    parser.add_argument("--skip-telegram", action="store_true")
    parser.add_argument("--opend-host", default=env.get("MOOMOO_OPEND_HOST", "127.0.0.1"))
    parser.add_argument("--opend-port", type=int, default=int(env.get("MOOMOO_OPEND_PORT", "11111")))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    run_ledger = args.run_ledger or args.output_dir / "catalyst-options-run-ledger.jsonl"
    mode = "dry-run" if args.dry_run or not args.post else "post"
    output_path = args.output_dir / "catalyst-options-screen.pdf"

    try:
        if args.fixture:
            client = FixtureCatalystOptionsProvider()
            report = build_catalyst_options_screen(client, DEFAULT_CANDIDATES)
        else:
            with MoomooOpenDQuoteClient(host=args.opend_host, port=args.opend_port) as client:
                report = build_catalyst_options_screen(client, DEFAULT_CANDIDATES)
    except Exception as exc:
        blocker = f"catalyst options screen failed: {exc}"
        write_run_ledger(
            run_ledger,
            status="failed",
            mode=mode,
            output_dir=args.output_dir,
            artifact_path=None,
            blocker=blocker,
        )
        print(blocker, file=sys.stderr)
        return 1

    metadata = {
        "generated_at": report.generated_at.strftime("%Y-%m-%d %H:%M:%S %Z").strip(),
        "universe": len(report.candidates),
        "ranked_ideas": len(report.ideas),
    }
    attachment = render_pdf_report("Catalyst Options Screen", catalyst_report_sections(report), metadata, output_path)
    caption = format_catalyst_telegram_html(report)

    if args.dry_run or not args.post:
        print(caption)
        print(f"attachment: {attachment}")
        write_run_ledger(
            run_ledger,
            status="succeeded",
            mode=mode,
            output_dir=args.output_dir,
            artifact_path=attachment,
            blocker=None,
        )
        return 0

    if args.skip_telegram or env.get("TELEGRAM_NOTIFY_ENABLED", "false").lower() != "true":
        blocker = (
            "telegram notification skipped: --skip-telegram was set"
            if args.skip_telegram
            else "telegram notification skipped: TELEGRAM_NOTIFY_ENABLED is not true"
        )
        print(blocker)
        write_run_ledger(
            run_ledger,
            status="skipped",
            mode=mode,
            output_dir=args.output_dir,
            artifact_path=attachment,
            blocker=blocker,
        )
        return 0
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "")
    if not token or token.startswith("replace-with-") or not chat_id or chat_id.startswith("replace-with-"):
        blocker = "telegram notification skipped: Telegram credentials are not configured"
        write_run_ledger(
            run_ledger,
            status="failed",
            mode=mode,
            output_dir=args.output_dir,
            artifact_path=attachment,
            blocker=blocker,
        )
        print(blocker, file=sys.stderr)
        return 1

    try:
        post_telegram_document(token, chat_id, attachment, caption=caption, parse_mode="HTML")
    except TelegramSendError as exc:
        blocker = f"telegram notification failed: {exc}"
        write_run_ledger(
            run_ledger,
            status="failed",
            mode=mode,
            output_dir=args.output_dir,
            artifact_path=attachment,
            blocker=blocker,
        )
        print(blocker, file=sys.stderr)
        return 1
    except (TimeoutError, urllib.error.URLError) as exc:
        blocker = f"telegram notification failed: {exc}"
        write_run_ledger(
            run_ledger,
            status="failed",
            mode=mode,
            output_dir=args.output_dir,
            artifact_path=attachment,
            blocker=blocker,
        )
        print(blocker, file=sys.stderr)
        return 1
    print("telegram report sent")
    write_run_ledger(
        run_ledger,
        status="succeeded",
        mode=mode,
        output_dir=args.output_dir,
        artifact_path=attachment,
        blocker=None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
