#!/usr/bin/env python3
"""Build and optionally send an options research report attachment."""

from __future__ import annotations

import argparse
import pathlib
import re
import sys
import urllib.error

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from quant_researcher_desk.moomoo_options_report import MoomooOpenDQuoteClient, OptionsReportError  # noqa: E402
from quant_researcher_desk.journal import OptionsJournalStore, entry_from_options_report  # noqa: E402
from quant_researcher_desk.options_research import (  # noqa: E402
    FixtureOptionsResearchProvider,
    OptionsResearchRequest,
    build_options_research_report,
    format_options_telegram_html,
    options_report_sections,
)
from quant_researcher_desk.reporting import (  # noqa: E402
    ReportRenderError,
    render_image_report,
    render_pdf_report,
    write_html_report,
)
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

    parser = argparse.ArgumentParser(description="Build an options pricing, scenario, and thesis report.")
    parser.add_argument("--dry-run", action="store_true", help="Print the Telegram caption and attachment path without posting.")
    parser.add_argument("--post", action="store_true", help="Post the report attachment when TELEGRAM_NOTIFY_ENABLED=true.")
    parser.add_argument("--fixture", action="store_true", help="Use deterministic local fixture data instead of Moomoo OpenD.")
    parser.add_argument("--symbol", default=env.get("MOOMOO_DEFAULT_SYMBOL", "US.TSM"))
    parser.add_argument("--option-code")
    parser.add_argument("--option-type", choices=("CALL", "PUT"), default="CALL")
    parser.add_argument("--strike", type=float)
    parser.add_argument("--expiry", help="Expiry date in YYYY-MM-DD format. Defaults to nearest future expiry.")
    parser.add_argument("--historical-volatility", type=float, default=0.35)
    parser.add_argument("--risk-free-rate", type=float, default=0.04)
    parser.add_argument("--output-dir", type=pathlib.Path, default=ROOT / "reports" / "options")
    parser.add_argument("--report-format", choices=("pdf", "html"), default="pdf")
    parser.add_argument("--persist-journal", action="store_true", help="Persist the generated report to the local options journal.")
    parser.add_argument("--journal-dir", type=pathlib.Path, default=ROOT / "reports" / "journal")
    parser.add_argument("--pricing-engine", choices=("legacy", "quantlib"), default="legacy")
    parser.add_argument("--shadow-compare", action="store_true", help="Add legacy-vs-QuantLib shadow comparison metadata and sections.")
    parser.add_argument(
        "--strategy-gate-passed",
        action="store_true",
        help="Render post-gate strategy comparison after the stock/tape/product gate has passed.",
    )
    parser.add_argument(
        "--strategy-gate-reason",
        default="Operator supplied stock/tape/product gate passed.",
        help="Short reason shown when post-gate strategy comparison is enabled.",
    )
    parser.add_argument(
        "--visual-explainer",
        action="store_true",
        help="Add Black-Scholes and Monte Carlo visual explainer sections to the report.",
    )
    parser.add_argument(
        "--render-image",
        action="store_true",
        help="Render/send a PNG preview using Playwright's managed Chromium only.",
    )
    parser.add_argument("--opend-host", default=env.get("MOOMOO_OPEND_HOST", "127.0.0.1"))
    parser.add_argument("--opend-port", type=int, default=int(env.get("MOOMOO_OPEND_PORT", "11111")))
    args = parser.parse_args()

    request = OptionsResearchRequest(
        symbol=args.symbol,
        option_code=args.option_code,
        option_type=args.option_type,
        strike=args.strike,
        expiry=args.expiry,
        historical_volatility=args.historical_volatility,
        risk_free_rate=args.risk_free_rate,
        pricing_engine=args.pricing_engine,
        shadow_compare=args.shadow_compare,
        strategy_gate_passed=args.strategy_gate_passed,
        strategy_gate_reason=args.strategy_gate_reason,
    )

    try:
        if args.fixture:
            report = build_options_research_report(FixtureOptionsResearchProvider(), request)
        else:
            with MoomooOpenDQuoteClient(host=args.opend_host, port=args.opend_port) as provider:
                report = build_options_research_report(provider, request)
    except (OptionsReportError, OSError) as exc:
        print(f"options research report failed: {exc}", file=sys.stderr)
        return 1

    title = f"{report.symbol} Options Research {report.contract.expiry} {report.contract.strike:g} {report.contract.option_type}"
    sections = options_report_sections(report, include_visual_explainer=args.visual_explainer)
    metadata = {
        "generated_at": report.generated_at.strftime("%Y-%m-%d %H:%M:%S %Z").strip(),
        "symbol": report.symbol,
        "contract": report.contract.code,
        "verdict": report.verdict,
        "pricing_engine": report.pricing_engine,
        "shadow_compare": "yes" if report.shadow_compare else "no",
        "shadow_status": (report.quantlib_vs_legacy_diff or {}).get("status", "off"),
        "strategy_gate": "passed" if report.strategy_gate_passed else "suppressed",
        "visual_explainer": "yes" if args.visual_explainer else "no",
    }
    attachment = render_attachment(title, sections, metadata, args.output_dir, args.report_format)
    preview_image = render_preview_image(title, sections, metadata, args.output_dir) if args.render_image else None
    caption = format_options_telegram_html(report, include_image=preview_image is not None)
    if args.persist_journal:
        journal_store = OptionsJournalStore(args.journal_dir)
        journal_entry = entry_from_options_report(report, attachment)
        journal_path = journal_store.upsert_entry(journal_entry)
        print(f"journal: {journal_path}#{journal_entry.id}")

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
            post_telegram_document(token, chat_id, attachment, caption="Detailed options report attached.")
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
