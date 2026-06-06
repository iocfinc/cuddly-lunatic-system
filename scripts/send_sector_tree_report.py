#!/usr/bin/env python3
"""Build and optionally send an industry/stock sector-tree report attachment."""

from __future__ import annotations

import argparse
import datetime as dt
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
    FixtureSectorTreeProvider,
    IndustryUniverseSectorTreeProvider,
    SectorTreeError,
    SectorTreeReport,
    SectorTreeRequest,
    build_sector_tree_report,
)
from quant_researcher_desk.industry_universe import load_industry_nodes_csv, priority_rotation_nodes  # noqa: E402
from quant_researcher_desk.sector_rotation import (  # noqa: E402
    SectorRotationEntry,
    SectorRotationState,
    load_sector_rotation_state,
    save_sector_rotation_state,
    select_rotation_entry_for_dispatch,
)
from scripts.telegram_notify import TelegramSendError, load_env, post_telegram_document, post_telegram_photo  # noqa: E402


UNIVERSE_NODES_PATH = ROOT / "data" / "sector-universe" / "value_chain_nodes.csv"
UNIVERSE_EDGES_PATH = ROOT / "data" / "sector-universe" / "value_chain_edges.csv"
ROTATION_STATE_PATH = ROOT / "reports" / "cron-state" / "sector-update.json"


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
                "gics_sector": profile.gics_sector or report.gics_sector or "local fixture",
                "gics_industry_group": profile.gics_industry_group or report.gics_industry_group or "local fixture",
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


def relationship_map(report: SectorTreeReport) -> dict[str, object]:
    def map_items(profiles) -> list[dict[str, str]]:  # type: ignore[no-untyped-def]
        return [
            {
                "symbol": profile.symbol,
                "name": profile.name,
                "industry": profile.gics_industry or profile.industry,
            }
            for profile in profiles
        ]

    return {
        "columns": [
            {"label": "Upstream", "items": map_items(report.upstream)},
            {"label": "Midstream", "items": map_items(report.midstream)},
            {"label": "Downstream", "items": map_items(report.downstream)},
        ],
        "edges": [
            {"source": edge.source_symbol, "target": edge.target_symbol, "relationship": edge.relationship}
            for edge in report.edges
        ],
    }


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
            "title": "GICS Relationship Map",
            "summary": "Industry-group view with industries or stocks as drill-down nodes. Arrows show the current evidence path; missing arrows are a sourcing queue, not a clean bill of isolation.",
            "relationship_map": relationship_map(report),
        },
        {
            "title": "Value-Chain Balance",
            "summary": f"Coverage-node count by role in this {report.analysis_level}. This is not a weighting model; it is a map of where the narrative currently has evidence.",
            "chart": {"rows": role_counts},
        },
        {"title": "Coverage Profiles", "table": company_rows(report)},
        {"title": "Relationship Tree", "table": relationship_rows(report)},
        {"title": "Risk Register", "items": list(report.risks)},
        {"title": "Telegram TLDR", "content": report.telegram_tldr},
        {"title": "Reader Copy", "content": report.marketing_copy},
    ]


def format_sector_telegram_html(report: SectorTreeReport, include_image: bool = True) -> str:
    tldr_lines = [line for line in report.telegram_tldr.splitlines() if "Educational research only" not in line]
    scope = report.gics_industry_group or report.request.sector.title()
    return "\n".join(
        [
            f"<b>{html.escape(report.request.market)} {html.escape(scope)} Desk Note</b>",
            f"Level: <code>{html.escape(report.analysis_level)}</code> | Nodes: <code>{len(report.upstream) + len(report.midstream) + len(report.downstream)}</code> | Relationships: <code>{len(report.edges)}</code>",
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


def load_universe_rotation() -> tuple[SectorRotationEntry, ...]:
    if not UNIVERSE_NODES_PATH.exists():
        return ()
    nodes = priority_rotation_nodes(load_industry_nodes_csv(UNIVERSE_NODES_PATH))
    return tuple(
        SectorRotationEntry(
            market=node.market,
            sector=node.gics_industry_group,
            note=f"GICS {node.gics_sector} industry group; representative industry {node.name} ({node.code}).",
        )
        for node in nodes
    )


def build_report_with_available_provider(request: SectorTreeRequest) -> SectorTreeReport:
    try:
        return build_sector_tree_report(request, FixtureSectorTreeProvider())
    except SectorTreeError:
        if not UNIVERSE_NODES_PATH.exists() or not UNIVERSE_EDGES_PATH.exists():
            raise
        return build_sector_tree_report(
            request,
            IndustryUniverseSectorTreeProvider(UNIVERSE_NODES_PATH, UNIVERSE_EDGES_PATH),
        )


def main() -> int:
    env = load_env(ROOT / ".env.example")
    env.update(load_env(ROOT / ".env"))

    parser = argparse.ArgumentParser(description="Build an industry value-chain tree report.")
    parser.add_argument("--dry-run", action="store_true", help="Print the Telegram caption and attachment path without posting.")
    parser.add_argument("--post", action="store_true", help="Post the report attachment when TELEGRAM_NOTIFY_ENABLED=true.")
    parser.add_argument("--market", default="US", help="Market code, for example US or HK.")
    parser.add_argument("--sector", default="semiconductors", help="Fixture-backed sector name.")
    parser.add_argument("--rotate", action="store_true", help="Use the configured daily HK/US sector rotation.")
    parser.add_argument(
        "--rotation-cadence-minutes",
        type=int,
        default=24 * 60,
        help="When rotating, advance the sector on this cadence. Default is daily.",
    )
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
    rotation_state: SectorRotationState | None = None
    if args.rotate:
        current_time = dt.datetime.now()
        universe_rotation = load_universe_rotation()
        if universe_rotation:
            rotation_entry, already_processed = select_rotation_entry_for_dispatch(
                current_time=current_time,
                rotation=universe_rotation,
                cadence_minutes=args.rotation_cadence_minutes,
                state_path=ROTATION_STATE_PATH,
            )
        else:
            rotation_entry, already_processed = select_rotation_entry_for_dispatch(
                current_time=current_time,
                cadence_minutes=args.rotation_cadence_minutes,
                state_path=ROTATION_STATE_PATH,
            )
        if already_processed:
            stored_state = load_sector_rotation_state(ROTATION_STATE_PATH)
            if stored_state is not None:
                print(
                    "sector rotation skipped: "
                    f"sent_at_epoch={stored_state.sent_at_epoch} market={stored_state.market} "
                    f"sector={stored_state.sector} cadence={stored_state.cadence_minutes}m already consumed"
                )
            else:
                print("sector rotation skipped: current cadence bucket already consumed")
            return 0
        market = rotation_entry.market
        sector = rotation_entry.sector
        rotation_state = SectorRotationState(
            sent_at_epoch=int(current_time.replace(second=0, microsecond=0).timestamp()),
            market=market,
            sector=sector,
            cadence_minutes=args.rotation_cadence_minutes,
        )
        print(
            f"sector rotation selected: {market} {sector} "
            f"(cadence={args.rotation_cadence_minutes}m) - {rotation_entry.note}"
        )

    request = SectorTreeRequest(
        market=market,
        sector=sector,
        focus_symbols=tuple(args.focus_symbol),
        max_companies_per_group=args.max_companies_per_group,
    )
    try:
        report = build_report_with_available_provider(request)
    except SectorTreeError as exc:
        print(f"sector tree report failed: {exc}", file=sys.stderr)
        return 1

    scope_title = report.gics_industry_group or report.request.sector.title()
    title = f"{report.request.market} {scope_title} {report.analysis_level.title()} Map"
    metadata = {
        "market": report.request.market,
        "analysis_level": report.analysis_level,
        "gics_sector": report.gics_sector or "local fixture",
        "gics_industry_group": report.gics_industry_group or "local fixture",
        "drill_down_industries": ", ".join(report.drill_down_industries) if report.drill_down_industries else "local fixture",
        "coverage_nodes": len(report.upstream) + len(report.midstream) + len(report.downstream),
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
        if rotation_state is not None:
            save_sector_rotation_state(ROTATION_STATE_PATH, rotation_state)
            print(f"rotation state saved: {ROTATION_STATE_PATH}")
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
