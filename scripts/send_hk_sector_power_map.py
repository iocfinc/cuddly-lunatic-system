#!/usr/bin/env python3
"""Build and optionally send an HK Finance breadth-first power-map report."""

from __future__ import annotations

import argparse
import pathlib
import re
import sys
import urllib.error

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from quant_researcher_desk.hk_sector_power_map import (  # noqa: E402
    FinancePowerMapError,
    FinancePowerMapRequest,
    build_hk_finance_power_map_report,
    finance_power_map_sections,
    format_hk_finance_telegram_html,
)
from quant_researcher_desk.reporting import ReportRenderError, render_image_report, render_pdf_report, write_html_report  # noqa: E402
from scripts.telegram_notify import TelegramSendError, load_env, post_telegram_document, post_telegram_photo  # noqa: E402


def slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9-]+", "-", value.strip()).strip("-").lower() or "report"


def render_attachment(
    title: str,
    sections: list[dict[str, object]],
    metadata: dict[str, object],
    output_dir: pathlib.Path,
    report_format: str,
) -> pathlib.Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    base = output_dir / slug(title)
    if report_format == "html":
        return write_html_report(title, sections, metadata, base.with_suffix(".html"))
    try:
        return render_pdf_report(title, sections, metadata, base.with_suffix(".pdf"))
    except ReportRenderError as exc:
        print(f"report PDF fallback: {exc}", file=sys.stderr)
        return base.with_suffix(".html")


def render_preview_image(
    title: str,
    sections: list[dict[str, object]],
    metadata: dict[str, object],
    output_dir: pathlib.Path,
) -> pathlib.Path | None:
    base = output_dir / slug(title)
    try:
        return render_image_report(title, sections, metadata, base.with_suffix(".png"))
    except ReportRenderError as exc:
        print(f"report image skipped: {exc}", file=sys.stderr)
        return None


def main() -> int:
    env = load_env(ROOT / ".env.example")
    env.update(load_env(ROOT / ".env"))

    parser = argparse.ArgumentParser(
        description="Build an HK Finance breadth-first power-map report.",
        epilog=(
            "Run:\n"
            "  uv --cache-dir .uv-cache run --python 3.10 python scripts/send_hk_sector_power_map.py --market HK --sector finance --dry-run\n"
            "  uv --cache-dir .uv-cache run --python 3.10 python scripts/send_hk_sector_power_map.py --market HK --sector finance --post"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dry-run", action="store_true", help="Print the Telegram caption and attachment path without posting.")
    parser.add_argument("--post", action="store_true", help="Post the report attachment when TELEGRAM_NOTIFY_ENABLED=true.")
    parser.add_argument("--market", default="HK", help="Market code, expected to be HK for this trial module.")
    parser.add_argument("--sector", default="finance", help="HK sector to map. The first trial supports finance only.")
    parser.add_argument("--output-dir", type=pathlib.Path, default=ROOT / "reports" / "hk-sector-power-map" / "finance")
    parser.add_argument("--report-format", choices=("pdf", "html"), default="pdf")
    parser.add_argument(
        "--render-image",
        action="store_true",
        help="Render/send a PNG preview using Playwright's managed Chromium only.",
    )
    args = parser.parse_args()

    request = FinancePowerMapRequest(market=args.market, sector=args.sector)
    try:
        report = build_hk_finance_power_map_report(request)
    except FinancePowerMapError as exc:
        print(f"hk finance power map failed: {exc}", file=sys.stderr)
        return 1

    title = "HK Finance Breadth-First Power Map"
    sections = finance_power_map_sections(report)
    metadata = {
        "generated_at": report.generated_at.strftime("%Y-%m-%d %H:%M:%S %Z").strip(),
        "market": report.request.market,
        "sector": report.request.sector,
        "nodes": len(report.upstream) + len(report.midstream) + len(report.downstream),
        "edges": len(report.edges),
        "tradingview_sector": report.tradingview_sector,
    }
    attachment = render_attachment(title, sections, metadata, args.output_dir, args.report_format)
    preview_image = render_preview_image(title, sections, metadata, args.output_dir) if args.render_image else None
    caption = format_hk_finance_telegram_html(report, include_image=preview_image is not None)

    if args.dry_run or not args.post:
        print(caption)
        if preview_image:
            print(f"image: {preview_image}")
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
        if preview_image:
            post_telegram_photo(token, chat_id, preview_image, caption=caption, parse_mode="HTML")
            post_telegram_document(token, chat_id, attachment, caption="HK Finance PDF report attached.")
        else:
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
