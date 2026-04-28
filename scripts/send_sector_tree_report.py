#!/usr/bin/env python3
"""Build and optionally send an industry/stock sector-tree report attachment."""

from __future__ import annotations

import argparse
import html
import pathlib
import re
import sys
import urllib.error

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from quant_researcher_desk.reporting import ReportRenderError, render_image_report, render_pdf_report, write_html_report  # noqa: E402
from quant_researcher_desk.sector_tree import (  # noqa: E402
    SectorTreeError,
    SectorTreeReport,
    SectorTreeRequest,
    build_sector_tree_report,
)
from quant_researcher_desk.sector_rotation import select_sector_rotation_entry  # noqa: E402
from scripts.telegram_notify import TelegramSendError, load_env, post_telegram_document, post_telegram_photo  # noqa: E402


def slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9-]+", "-", value.strip()).strip("-").lower() or "report"


def company_rows(report: SectorTreeReport) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for profile in (*report.upstream, *report.midstream, *report.downstream):
        rows.append(
            {
                "role": profile.value_chain_role,
                "symbol": profile.symbol,
                "name": profile.name,
                "industry": profile.industry,
                "summary": profile.business_summary,
            }
        )
    return rows


def relationship_rows(report: SectorTreeReport) -> list[dict[str, str]]:
    return [
        {
            "source": edge.source_symbol,
            "target": edge.target_symbol,
            "relationship": edge.relationship,
            "evidence": edge.evidence,
            "risk": edge.risk_note,
        }
        for edge in report.edges
    ]


def sector_report_sections(report: SectorTreeReport) -> list[dict[str, object]]:
    role_counts = [
        {"label": "Upstream", "value": len(report.upstream)},
        {"label": "Midstream", "value": len(report.midstream)},
        {"label": "Downstream", "value": len(report.downstream)},
    ]
    return [
        {
            "title": "Sector Thesis",
            "content": (
                f"{report.educational_summary}\n\n"
                "Read the tree from left to right: supply first, platform control second, consumer or enterprise demand last."
            ),
        },
        {
            "title": "Value-Chain Balance",
            "summary": "Company count by role in this report. This is not a weighting model; it is a map of where the narrative currently has evidence.",
            "chart": {"rows": role_counts},
        },
        {"title": "Company Profiles", "table": company_rows(report)},
        {"title": "Relationship Tree", "table": relationship_rows(report)},
        {"title": "Risk Register", "items": list(report.risks)},
        {"title": "Telegram TLDR", "content": report.telegram_tldr},
        {"title": "Reader Copy", "content": report.marketing_copy},
    ]


def format_sector_telegram_html(report: SectorTreeReport, include_image: bool = True) -> str:
    tldr_lines = [line for line in report.telegram_tldr.splitlines() if "Educational research only" not in line]
    return "\n".join(
        [
            f"<b>{html.escape(report.request.market)} {html.escape(report.request.sector.title())} Sector Desk Note</b>",
            f"Companies: <code>{len(report.upstream) + len(report.midstream) + len(report.downstream)}</code> | Relationships: <code>{len(report.edges)}</code>",
            "",
            html.escape("\n".join(tldr_lines)),
            "",
            "Full image/report attached." if include_image else "Full report attached.",
            "Educational research only, not a trading instruction.",
        ]
    )


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

    parser = argparse.ArgumentParser(description="Build an industry value-chain tree report.")
    parser.add_argument("--dry-run", action="store_true", help="Print the Telegram caption and attachment path without posting.")
    parser.add_argument("--post", action="store_true", help="Post the report attachment when TELEGRAM_NOTIFY_ENABLED=true.")
    parser.add_argument("--market", default="US", help="Market code, for example US or HK.")
    parser.add_argument("--sector", default="semiconductors", help="Fixture-backed sector name.")
    parser.add_argument("--rotate", action="store_true", help="Use the configured daily HK/US sector rotation.")
    parser.add_argument("--focus-symbol", action="append", default=[], help="Optional symbol to include; repeat for multiple symbols.")
    parser.add_argument("--max-companies-per-group", type=int)
    parser.add_argument("--output-dir", type=pathlib.Path, default=ROOT / "reports" / "sector-tree")
    parser.add_argument("--report-format", choices=("pdf", "html"), default="pdf")
    parser.add_argument(
        "--render-image",
        action="store_true",
        help="Render/send a PNG preview using Playwright's managed Chromium only.",
    )
    args = parser.parse_args()

    market = args.market
    sector = args.sector
    if args.rotate:
        rotation_entry = select_sector_rotation_entry()
        market = rotation_entry.market
        sector = rotation_entry.sector
        print(f"sector rotation selected: {market} {sector} - {rotation_entry.note}")

    request = SectorTreeRequest(
        market=market,
        sector=sector,
        focus_symbols=tuple(args.focus_symbol),
        max_companies_per_group=args.max_companies_per_group,
    )
    try:
        report = build_sector_tree_report(request)
    except SectorTreeError as exc:
        print(f"sector tree report failed: {exc}", file=sys.stderr)
        return 1

    title = f"{report.request.market} {report.request.sector.title()} Sector Tree"
    metadata = {
        "market": report.request.market,
        "sector": report.request.sector.title(),
        "companies": len(report.upstream) + len(report.midstream) + len(report.downstream),
        "relationships": len(report.edges),
    }
    sections = sector_report_sections(report)
    attachment = render_attachment(title, sections, metadata, args.output_dir, args.report_format)
    preview_image = render_preview_image(title, sections, metadata, args.output_dir) if args.render_image else None
    caption = format_sector_telegram_html(report, include_image=preview_image is not None)

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
            post_telegram_document(token, chat_id, attachment, caption="Detailed sector report attached.")
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
