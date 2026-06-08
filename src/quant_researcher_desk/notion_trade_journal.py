"""Notion Trade Journal sync helpers for weekly options packets and TradingAgents reports."""

from __future__ import annotations

import copy
import dataclasses
import datetime as dt
import os
import pathlib
import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Protocol

from quant_researcher_desk.moomoo_options_report import MoomooOpenDQuoteClient, get_first
from quant_researcher_desk.options_research import OptionsResearchReport
from quant_researcher_desk.weekly_options_packet import WeeklyOptionsPacket, WeeklyOptionsTearSheet
from quant_researcher_desk.weekly_options_screener import ScreenedOption, shortlist_rows

MAX_NOTION_TEXT_LENGTH = 1800
NOTION_APPEND_CHUNK = 100
TRADINGAGENTS_REPORT_DIR_PATTERN = re.compile(r"^(?P<ticker>.+)_(?P<date>\d{8})_(?P<time>\d{6})$")
DECISION_WORD_PATTERN = re.compile(
    r"\b(strong buy|buy|overweight|outperform|hold|neutral|market perform|underweight|sell|reduce|avoid)\b",
    flags=re.IGNORECASE,
)

REQUIRED_TRADE_JOURNAL_PROPERTIES: dict[str, set[str]] = {
    "Name": {"title"},
    "Date": {"date"},
    "Tags": {"select", "multi_select", "status"},
    "Entry Type": {"select", "rich_text", "status", "multi_select"},
    "Source": {"select", "rich_text", "status", "multi_select"},
    "Ticker": {"select", "rich_text", "multi_select"},
    "Option Side": {"select", "rich_text", "status", "multi_select"},
    "Recommendation": {"select", "rich_text", "status", "multi_select"},
    "Run Key": {"rich_text", "select"},
    "Run Path": {"rich_text", "url"},
    "External ID": {"rich_text", "title"},
}


class NotionSyncError(Exception):
    """Raised when Notion sync cannot proceed."""


class NotionSchemaError(NotionSyncError):
    """Raised when the target Notion database schema is incomplete."""


@dataclass(frozen=True)
class NotionSyncConfig:
    enabled: bool
    dry_run: bool
    api_token: str
    trade_journal_database_id: str
    template_page_id: str | None
    opend_host: str = "127.0.0.1"
    opend_port: int = 11111


@dataclass(frozen=True)
class NotionEntryPayload:
    title: str
    date: str
    entry_type: str
    source: str
    external_id: str
    run_key: str
    run_path: str
    blocks: tuple[dict[str, Any], ...]
    ticker: str | None = None
    option_side: str | None = None
    recommendation: str | None = None
    tags: tuple[str, ...] = ("Done",)


@dataclass(frozen=True)
class WeeklyRunEntry:
    title: str
    date: str
    run_key: str
    run_path: str
    external_id: str
    packet_title: str
    generated_at: dt.datetime
    market: str
    target_count: int
    shortlisted_count: int
    skipped_count: int
    pricing_engine: str
    shadow_compare: bool
    methodology_summary: str
    executive_summary: str
    analysis_mode: str
    stock_review_enabled: bool
    discovery_stats: dict[str, int]
    shortlist: tuple[dict[str, Any], ...]
    review_summary: str | None = None
    warnings: tuple[str, ...] = ()
    attachment_path: str | None = None


@dataclass(frozen=True)
class WeeklyTearSheetEntry:
    title: str
    date: str
    run_key: str
    run_path: str
    external_id: str
    ticker: str
    option_side: str
    report: OptionsResearchReport
    screened_option: ScreenedOption
    writer_summary: str
    attachment_path: str | None = None


@dataclass(frozen=True)
class TradingAgentsEntry:
    title: str
    date: str
    run_key: str
    run_path: str
    external_id: str
    ticker: str
    stock_name: str
    recommendation: str | None
    report_markdown: str


@dataclass(frozen=True)
class SyncResult:
    action: str
    external_id: str
    title: str
    page_id: str | None
    dry_run: bool
    message: str


class NotionClientProtocol(Protocol):
    databases: Any
    pages: Any
    blocks: Any


def load_notion_sync_config(env: dict[str, str] | None = None) -> NotionSyncConfig:
    values = env or os.environ
    return NotionSyncConfig(
        enabled=_env_flag(values.get("NOTION_SYNC_ENABLED"), default=False),
        dry_run=_env_flag(values.get("NOTION_SYNC_DRY_RUN"), default=False),
        api_token=(values.get("NOTION_API_TOKEN") or "").strip(),
        trade_journal_database_id=(values.get("NOTION_TRADE_JOURNAL_DATABASE_ID") or "").strip(),
        template_page_id=(values.get("NOTION_TEMPLATE_PAGE_ID") or "").strip() or None,
        opend_host=(values.get("MOOMOO_OPEND_HOST") or "127.0.0.1").strip() or "127.0.0.1",
        opend_port=int((values.get("MOOMOO_OPEND_PORT") or "11111").strip() or "11111"),
    )


def _env_flag(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def create_notion_client(config: NotionSyncConfig) -> NotionClientProtocol:
    if not config.api_token:
        raise NotionSyncError("NOTION_API_TOKEN is required for Notion sync.")
    try:
        from notion_client import Client  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise NotionSyncError("notion-client is not installed. Add the dependency before running Notion sync.") from exc
    return Client(auth=config.api_token)


def require_notion_ready(config: NotionSyncConfig) -> None:
    if not config.trade_journal_database_id:
        raise NotionSyncError("NOTION_TRADE_JOURNAL_DATABASE_ID is required for Notion sync.")
    if not config.api_token:
        raise NotionSyncError("NOTION_API_TOKEN is required for Notion sync.")


def weekly_run_external_id(run_key: str) -> str:
    return f"weekly-run:{run_key}"


def weekly_tearsheet_external_id(run_key: str, option_code: str) -> str:
    return f"weekly-tearsheet:{run_key}:{option_code}"


def tradingagents_external_id(folder_name: str) -> str:
    return f"tradingagents:{folder_name}"


def weekly_packet_run_key(packet: WeeklyOptionsPacket) -> str:
    return packet.generated_at.strftime("%Y%m%d_%H%M%S")


def build_weekly_run_entry(
    packet: WeeklyOptionsPacket,
    *,
    run_path: pathlib.Path,
    attachment_path: pathlib.Path | None = None,
) -> WeeklyRunEntry:
    run_key = weekly_packet_run_key(packet)
    rows = shortlist_rows(packet.weekly_result)
    return WeeklyRunEntry(
        title=f"Weekly Options Screen - {packet.generated_at.date().isoformat()}",
        date=packet.generated_at.date().isoformat(),
        run_key=run_key,
        run_path=str(run_path),
        external_id=weekly_run_external_id(run_key),
        packet_title=packet.title,
        generated_at=packet.generated_at,
        market=packet.weekly_result.request.market,
        target_count=packet.weekly_result.request.top_n,
        shortlisted_count=len(packet.weekly_result.ranked_options),
        skipped_count=len(packet.weekly_result.skipped_underlyings),
        pricing_engine=packet.weekly_result.pricing_engine,
        shadow_compare=packet.weekly_result.shadow_compare,
        methodology_summary=packet.methodology_summary,
        executive_summary=packet.executive_summary,
        analysis_mode=packet.weekly_result.request.analysis_mode,
        stock_review_enabled=packet.weekly_result.request.stock_review,
        discovery_stats=dict(packet.weekly_result.discovery_stats),
        shortlist=tuple({"rank": index, **row} for index, row in enumerate(rows, start=1)),
        review_summary=packet.weekly_result.review_summary,
        warnings=packet.warnings,
        attachment_path=str(attachment_path) if attachment_path else None,
    )


def build_weekly_tearsheet_entries(
    packet: WeeklyOptionsPacket,
    *,
    run_path: pathlib.Path,
    attachment_path: pathlib.Path | None = None,
) -> list[WeeklyTearSheetEntry]:
    run_key = weekly_packet_run_key(packet)
    entries: list[WeeklyTearSheetEntry] = []
    for tearsheet, screened_option in zip(packet.tearsheets, packet.weekly_result.ranked_options):
        title = (
            f"{screened_option.symbol} {screened_option.side} "
            f"{screened_option.expiry} {_format_strike(screened_option.strike)}"
        )
        entries.append(
            WeeklyTearSheetEntry(
                title=title,
                date=packet.generated_at.date().isoformat(),
                run_key=run_key,
                run_path=str(run_path),
                external_id=weekly_tearsheet_external_id(run_key, screened_option.option_code),
                ticker=screened_option.symbol,
                option_side=screened_option.side,
                report=tearsheet.report,
                screened_option=screened_option,
                writer_summary=tearsheet.writer_copy.executive_summary,
                attachment_path=str(attachment_path) if attachment_path else None,
            )
        )
    return entries


def render_weekly_run_payload(entry: WeeklyRunEntry) -> NotionEntryPayload:
    stats_rows = [
        {
            "Generated At": entry.generated_at.strftime("%Y-%m-%d %H:%M:%S %Z").strip(),
            "Market": entry.market,
            "Packet": entry.packet_title,
            "Analysis Mode": entry.analysis_mode,
        },
        {
            "Target": str(entry.target_count),
            "Shortlisted": str(entry.shortlisted_count),
            "Skipped": str(entry.skipped_count),
            "Pricing Engine": entry.pricing_engine,
        },
        {
            "Shadow Compare": "Yes" if entry.shadow_compare else "No",
            "Stock Review": "Enabled" if entry.stock_review_enabled else "Disabled",
            "Reviewed": entry.review_summary or "No reviewer summary",
            "Warnings": "; ".join(entry.warnings) or "None",
        },
    ]
    discovery_row = {key.replace("_", " ").title(): str(value) for key, value in sorted(entry.discovery_stats.items())}
    shortlist_headers = [
        "rank",
        "symbol",
        "side",
        "expiry",
        "strike",
        "premium",
        "trend_regime",
        "stock_direction",
        "fair_value_gap_pct",
        "valuation_view",
        "review_status",
    ]
    shortlist_table = [
        {header.replace("_", " ").title(): _format_shortlist_value(row.get(header)) for header in shortlist_headers}
        for row in entry.shortlist
    ]
    blocks: list[dict[str, Any]] = []
    blocks.extend(_heading_block("heading_2", "Stock-First Methodology"))
    blocks.extend(_paragraph_blocks(entry.executive_summary))
    blocks.extend(_paragraph_blocks(entry.methodology_summary))
    blocks.extend(
        _bulleted_list_blocks(
            [
                "The weekly run starts with stock context, then moves to contract selection and valuation.",
                "Composite score is a review-priority signal, not a trading instruction.",
                "Shortlisted names survive stock-context gating before option-level tear sheets are produced.",
            ]
        )
    )
    blocks.extend(_heading_block("heading_2", "Run Stats"))
    blocks.append(_table_block_from_dict_rows(stats_rows))
    if discovery_row:
        blocks.extend(_heading_block("heading_3", "Discovery Counters"))
        blocks.append(_table_block_from_dict_rows([discovery_row]))
    blocks.extend(_heading_block("heading_2", "Shortlist"))
    if shortlist_table:
        blocks.append(_table_block_from_dict_rows(shortlist_table))
    else:
        blocks.extend(_paragraph_blocks("No contracts passed the current gating rules for this run."))
    blocks.extend(_heading_block("heading_2", "Artifacts"))
    artifact_items = [f"Run path: {entry.run_path}"]
    if entry.attachment_path:
        artifact_items.append(f"Packet attachment: {entry.attachment_path}")
    blocks.extend(_bulleted_list_blocks(artifact_items))
    blocks.extend(_heading_block("heading_2", "Stock-Context Gating"))
    blocks.extend(
        _paragraph_blocks(
            "Names with mixed trend regime, missing daily bars, weak liquidity, or side misalignment are filtered out early. "
            "That keeps the tear sheets focused on contracts where stock direction, timing, and valuation can be reviewed together."
        )
    )
    return NotionEntryPayload(
        title=entry.title,
        date=entry.date,
        entry_type="Weekly Run",
        source="naval-analyst",
        external_id=entry.external_id,
        run_key=entry.run_key,
        run_path=entry.run_path,
        blocks=tuple(blocks),
    )


def render_weekly_tearsheet_payload(entry: WeeklyTearSheetEntry) -> NotionEntryPayload:
    report = entry.report
    option = entry.screened_option
    stock_context_row = {
        "Trend Regime": option.trend_regime,
        "Stock Direction": option.stock_direction,
        "Stock Review Summary": option.stock_review_summary,
        "Invalidation": option.invalidation,
        "Catalyst View": option.catalyst_view,
        "Alignment Status": option.alignment_status,
    }
    contract_row = {
        "Contract": report.contract.code,
        "Expiry": report.contract.expiry,
        "Strike": _format_strike(report.contract.strike),
        "Premium": _format_decimal(report.contract.market_price),
        "Underlying": _format_decimal(report.underlying_price),
        "Verdict": report.verdict,
        "Valuation View": report.valuation_view,
        "Fair Value Gap": _format_percent(report.fair_value_gap_pct),
    }
    pricing_row = {
        "Black-Scholes": _format_decimal(report.model.theoretical_value),
        "Model Edge": _format_decimal(report.model_edge),
        "Model Edge %": _format_percent(report.model_edge_pct),
        "Monte Carlo Mid": _format_decimal(_distribution_midpoint(report.monte_carlo_distribution)),
    }
    liquidity_row = {
        "Volume": str(report.contract.volume),
        "Open Interest": str(report.contract.open_interest),
        "Delta": _format_decimal(report.contract.delta),
        "Premium": _format_decimal(report.contract.market_price),
    }
    volatility_row = {
        "Implied Volatility": _format_percent(report.implied_volatility_used),
        "Historical Volatility": _format_percent(report.historical_volatility),
        "Years To Expiry": _format_decimal(report.years_to_expiry),
        "Risk-Free Rate": _format_percent(report.risk_free_rate),
    }
    review_items = [
        f"Review status: {option.review_status}",
        f"Review flags: {', '.join(option.review_flags) if option.review_flags else 'None'}",
        f"Review notes: {option.review_notes or 'None'}",
        f"Writer summary: {entry.writer_summary}",
    ]
    if report.risks:
        review_items.extend(f"Risk: {risk}" for risk in report.risks)
    artifact_items = [
        f"Run path: {entry.run_path}",
        f"Contract code: {report.contract.code}",
    ]
    if entry.attachment_path:
        artifact_items.append(f"Packet attachment: {entry.attachment_path}")
    blocks: list[dict[str, Any]] = []
    blocks.extend(_heading_block("heading_2", "Stock Context"))
    blocks.append(_table_block_from_dict_rows([stock_context_row]))
    blocks.extend(_heading_block("heading_2", "Contract Summary"))
    blocks.append(_table_block_from_dict_rows([contract_row]))
    blocks.extend(_heading_block("heading_2", "Pricing, Liquidity, and IV-HV"))
    blocks.append(_table_block_from_dict_rows([pricing_row]))
    blocks.append(_table_block_from_dict_rows([liquidity_row]))
    blocks.append(_table_block_from_dict_rows([volatility_row]))
    blocks.extend(_heading_block("heading_2", "Reviewer and Alignment Status"))
    blocks.extend(_bulleted_list_blocks(review_items))
    blocks.extend(_heading_block("heading_2", "Artifacts"))
    blocks.extend(_bulleted_list_blocks(artifact_items))
    return NotionEntryPayload(
        title=entry.title,
        date=entry.date,
        entry_type="Weekly Tear Sheet",
        source="naval-analyst",
        external_id=entry.external_id,
        run_key=entry.run_key,
        run_path=entry.run_path,
        ticker=entry.ticker,
        option_side=entry.option_side,
        blocks=tuple(blocks),
    )


def render_tradingagents_payload(entry: TradingAgentsEntry) -> NotionEntryPayload:
    return NotionEntryPayload(
        title=entry.title,
        date=entry.date,
        entry_type="Stock Analysis",
        source="TradingAgents",
        external_id=entry.external_id,
        run_key=entry.run_key,
        run_path=entry.run_path,
        ticker=entry.ticker,
        recommendation=entry.recommendation,
        blocks=tuple(markdown_to_notion_blocks(entry.report_markdown)),
    )


def sync_payloads(
    client: NotionClientProtocol,
    config: NotionSyncConfig,
    payloads: Iterable[NotionEntryPayload],
) -> list[SyncResult]:
    require_notion_ready(config)
    schema = validate_trade_journal_schema(client, config.trade_journal_database_id)
    template_blocks = fetch_template_blocks(client, config.template_page_id) if config.template_page_id else []
    results: list[SyncResult] = []
    for payload in payloads:
        results.append(sync_payload(client, config, schema, payload, template_blocks=template_blocks))
    return results


def sync_payload(
    client: NotionClientProtocol,
    config: NotionSyncConfig,
    schema: dict[str, str],
    payload: NotionEntryPayload,
    *,
    template_blocks: list[dict[str, Any]] | None = None,
) -> SyncResult:
    existing_page = find_page_by_external_id(client, config.trade_journal_database_id, payload.external_id)
    properties = build_page_properties(payload, schema)
    blocks = [*copy.deepcopy(template_blocks or []), *copy.deepcopy(list(payload.blocks))]
    if config.dry_run:
        action = "preview-update" if existing_page else "preview-create"
        return SyncResult(
            action=action,
            external_id=payload.external_id,
            title=payload.title,
            page_id=(existing_page or {}).get("id"),
            dry_run=True,
            message=f"{action}: {payload.title}",
        )
    if existing_page:
        page_id = str(existing_page["id"])
        client.pages.update(page_id=page_id, properties=properties)
        replace_page_children(client, page_id, blocks)
        return SyncResult(
            action="updated",
            external_id=payload.external_id,
            title=payload.title,
            page_id=page_id,
            dry_run=False,
            message=f"updated: {payload.title}",
        )
    page = client.pages.create(
        parent={"database_id": config.trade_journal_database_id},
        properties=properties,
        children=blocks[:NOTION_APPEND_CHUNK],
    )
    page_id = str(page["id"])
    if len(blocks) > NOTION_APPEND_CHUNK:
        append_page_children(client, page_id, blocks[NOTION_APPEND_CHUNK:])
    return SyncResult(
        action="created",
        external_id=payload.external_id,
        title=payload.title,
        page_id=page_id,
        dry_run=False,
        message=f"created: {payload.title}",
    )


def validate_trade_journal_schema(client: NotionClientProtocol, database_id: str) -> dict[str, str]:
    response = client.databases.retrieve(database_id=database_id)
    properties = response.get("properties", {})
    schema: dict[str, str] = {}
    missing: list[str] = []
    invalid: list[str] = []
    for name, allowed_types in REQUIRED_TRADE_JOURNAL_PROPERTIES.items():
        property_payload = properties.get(name)
        if not property_payload:
            missing.append(name)
            continue
        property_type = str(property_payload.get("type", "")).strip()
        if property_type not in allowed_types:
            invalid.append(f"{name}={property_type}")
            continue
        schema[name] = property_type
    if missing or invalid:
        details = []
        if missing:
            details.append(f"missing properties: {', '.join(missing)}")
        if invalid:
            details.append(f"unsupported property types: {', '.join(invalid)}")
        raise NotionSchemaError(
            "Trade Journal database schema is not ready. Add the required properties before syncing; "
            + "; ".join(details)
            + "."
        )
    return schema


def build_page_properties(payload: NotionEntryPayload, schema: dict[str, str]) -> dict[str, Any]:
    values: dict[str, Any] = {
        "Name": payload.title,
        "Date": payload.date,
        "Tags": list(payload.tags),
        "Entry Type": payload.entry_type,
        "Source": payload.source,
        "Ticker": payload.ticker,
        "Option Side": payload.option_side,
        "Recommendation": payload.recommendation,
        "Run Key": payload.run_key,
        "Run Path": payload.run_path,
        "External ID": payload.external_id,
    }
    properties: dict[str, Any] = {}
    for name, value in values.items():
        if value in (None, "", []):
            continue
        properties[name] = _property_value_for_schema(schema[name], value)
    return properties


def _property_value_for_schema(property_type: str, value: Any) -> dict[str, Any]:
    if property_type == "title":
        return {"title": _rich_text(value)}
    if property_type == "rich_text":
        return {"rich_text": _rich_text(value)}
    if property_type == "date":
        return {"date": {"start": str(value)}}
    if property_type == "select":
        return {"select": {"name": str(value)}}
    if property_type == "multi_select":
        items = value if isinstance(value, (list, tuple)) else [value]
        return {"multi_select": [{"name": str(item)} for item in items if str(item).strip()]}
    if property_type == "status":
        return {"status": {"name": str(value if not isinstance(value, (list, tuple)) else value[0])}}
    if property_type == "url":
        return {"url": str(value)}
    raise NotionSchemaError(f"Unsupported property type for Trade Journal sync: {property_type}")


def find_page_by_external_id(client: NotionClientProtocol, database_id: str, external_id: str) -> dict[str, Any] | None:
    response = client.databases.query(
        database_id=database_id,
        filter={"property": "External ID", "rich_text": {"equals": external_id}},
        page_size=1,
    )
    results = response.get("results", [])
    if results:
        return results[0]
    response = client.databases.query(
        database_id=database_id,
        filter={"property": "External ID", "title": {"equals": external_id}},
        page_size=1,
    )
    results = response.get("results", [])
    return results[0] if results else None


def fetch_template_blocks(client: NotionClientProtocol, template_page_id: str | None) -> list[dict[str, Any]]:
    if not template_page_id:
        return []
    return [_clone_block_for_append(client, block) for block in list_block_children(client, template_page_id)]


def list_block_children(client: NotionClientProtocol, block_id: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        response = client.blocks.children.list(block_id=block_id, start_cursor=cursor)
        results.extend(response.get("results", []))
        if not response.get("has_more"):
            break
        cursor = response.get("next_cursor")
    return results


def _clone_block_for_append(client: NotionClientProtocol, block: dict[str, Any]) -> dict[str, Any]:
    block_type = str(block.get("type", "")).strip()
    if not block_type or block_type not in block:
        return _paragraph_block(f"Unsupported template block: {block_type or 'unknown'}")
    payload = copy.deepcopy(block.get(block_type, {}))
    clean_block = {"object": "block", "type": block_type, block_type: payload}
    if block.get("has_children"):
        children = [_clone_block_for_append(client, child) for child in list_block_children(client, str(block["id"]))]
        clean_block[block_type]["children"] = children
    for key in ("id", "parent", "created_time", "created_by", "last_edited_time", "archived", "in_trash", "has_children"):
        clean_block.pop(key, None)
    return clean_block


def replace_page_children(client: NotionClientProtocol, page_id: str, blocks: list[dict[str, Any]]) -> None:
    for block in list_block_children(client, page_id):
        block_id = str(block.get("id", ""))
        if not block_id:
            continue
        if hasattr(client.blocks, "delete"):
            client.blocks.delete(block_id=block_id)
        else:
            client.blocks.update(block_id=block_id, archived=True)
    append_page_children(client, page_id, blocks)


def append_page_children(client: NotionClientProtocol, page_id: str, blocks: list[dict[str, Any]]) -> None:
    for start in range(0, len(blocks), NOTION_APPEND_CHUNK):
        chunk = blocks[start : start + NOTION_APPEND_CHUNK]
        if chunk:
            client.blocks.children.append(block_id=page_id, children=chunk)


def markdown_to_notion_blocks(markdown: str) -> list[dict[str, Any]]:
    lines = markdown.splitlines()
    blocks: list[dict[str, Any]] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped:
            index += 1
            continue
        heading_match = re.match(r"^(#{1,3})\s+(.*)$", stripped)
        if heading_match:
            level = len(heading_match.group(1))
            blocks.extend(_heading_block(f"heading_{level}", heading_match.group(2).strip()))
            index += 1
            continue
        if _looks_like_markdown_table(lines, index):
            table_lines: list[str] = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_lines.append(lines[index].strip())
                index += 1
            blocks.append(_table_block_from_matrix(_parse_markdown_table(table_lines)))
            continue
        list_match = re.match(r"^([-*]|\d+\.)\s+(.*)$", stripped)
        if list_match:
            list_lines: list[str] = []
            while index < len(lines):
                candidate = lines[index].strip()
                if not candidate:
                    break
                if not re.match(r"^([-*]|\d+\.)\s+(.*)$", candidate):
                    break
                list_lines.append(candidate)
                index += 1
            for item in list_lines:
                item_match = re.match(r"^([-*]|\d+\.)\s+(.*)$", item)
                assert item_match is not None
                content = item_match.group(2).strip()
                if re.match(r"^\d+\.$", item_match.group(1)):
                    blocks.append(_list_item_block("numbered_list_item", content))
                else:
                    blocks.append(_list_item_block("bulleted_list_item", content))
            continue
        paragraph_lines = [stripped]
        index += 1
        while index < len(lines):
            candidate = lines[index].strip()
            if not candidate:
                index += 1
                break
            if re.match(r"^(#{1,3})\s+", candidate) or _looks_like_markdown_table(lines, index) or re.match(r"^([-*]|\d+\.)\s+", candidate):
                break
            paragraph_lines.append(candidate)
            index += 1
        blocks.extend(_paragraph_blocks(" ".join(paragraph_lines)))
    return blocks


def _looks_like_markdown_table(lines: list[str], index: int) -> bool:
    if index + 1 >= len(lines):
        return False
    current = lines[index].strip()
    separator = lines[index + 1].strip()
    if not current.startswith("|") or not separator.startswith("|"):
        return False
    return bool(re.match(r"^\|?[\s:-]+\|[\s|:-]*$", separator))


def _parse_markdown_table(lines: list[str]) -> list[list[str]]:
    rows: list[list[str]] = []
    for raw_line in lines:
        parts = [part.strip() for part in raw_line.strip().strip("|").split("|")]
        rows.append(parts)
    if len(rows) >= 2:
        rows.pop(1)
    return rows


def build_weekly_sync_payloads(
    packet: WeeklyOptionsPacket,
    *,
    run_path: pathlib.Path,
    attachment_path: pathlib.Path | None = None,
) -> list[NotionEntryPayload]:
    run_entry = build_weekly_run_entry(packet, run_path=run_path, attachment_path=attachment_path)
    tear_entries = build_weekly_tearsheet_entries(packet, run_path=run_path, attachment_path=attachment_path)
    return [render_weekly_run_payload(run_entry), *(render_weekly_tearsheet_payload(entry) for entry in tear_entries)]


def parse_tradingagents_report_directory(path: pathlib.Path) -> tuple[str, dt.datetime, str]:
    folder_name = path.parent.name
    match = TRADINGAGENTS_REPORT_DIR_PATTERN.match(folder_name)
    if not match:
        raise ValueError(f"Unsupported TradingAgents report folder name: {folder_name}")
    ticker = match.group("ticker")
    run_time = dt.datetime.strptime(f"{match.group('date')}_{match.group('time')}", "%Y%m%d_%H%M%S")
    run_time = run_time.replace(tzinfo=dt.timezone.utc)
    return ticker, run_time, folder_name


def discover_tradingagents_reports(
    reports_root: pathlib.Path,
    *,
    since: dt.datetime | dt.date | None = None,
    limit: int | None = None,
) -> list[pathlib.Path]:
    reports = sorted(reports_root.glob("*/complete_report.md"))
    selected: list[pathlib.Path] = []
    for path in reports:
        try:
            _, run_time, _ = parse_tradingagents_report_directory(path)
        except ValueError:
            continue
        if since is not None:
            if isinstance(since, dt.datetime):
                threshold = since if since.tzinfo is not None else since.replace(tzinfo=dt.timezone.utc)
            else:
                threshold = dt.datetime.combine(since, dt.time.min, tzinfo=dt.timezone.utc)
            if run_time < threshold:
                continue
        selected.append(path)
    if limit is not None:
        return selected[:limit]
    return selected


def extract_recommendation_from_markdown(markdown: str) -> str | None:
    portfolio_section = _extract_markdown_section(markdown, "## V. Portfolio Manager Decision")
    recommendation = _extract_decision_word(portfolio_section) if portfolio_section else None
    if recommendation:
        return recommendation
    for heading in ("## III. Trading Team Plan", "## II. Research Team Decision", "## Final Recommendation"):
        section = _extract_markdown_section(markdown, heading)
        recommendation = _extract_decision_word(section) if section else None
        if recommendation:
            return recommendation
    return None


def _extract_markdown_section(markdown: str, heading: str) -> str | None:
    pattern = re.compile(rf"^{re.escape(heading)}\s*$", flags=re.MULTILINE)
    match = pattern.search(markdown)
    if not match:
        return None
    start = match.end()
    next_heading = re.search(r"^##\s+.+$", markdown[start:], flags=re.MULTILINE)
    if not next_heading:
        return markdown[start:].strip()
    return markdown[start : start + next_heading.start()].strip()


def _extract_decision_word(text: str | None) -> str | None:
    if not text:
        return None
    for line in text.splitlines():
        if "analyst" in line.lower() and "final transaction proposal" in line.lower():
            continue
        match = DECISION_WORD_PATTERN.search(line)
        if match:
            return _normalize_recommendation(match.group(1))
    match = DECISION_WORD_PATTERN.search(text)
    if match:
        return _normalize_recommendation(match.group(1))
    return None


def _normalize_recommendation(value: str) -> str:
    normalized = value.strip().upper()
    replacements = {
        "STRONG BUY": "BUY",
        "OUTPERFORM": "BUY",
        "MARKET PERFORM": "HOLD",
        "NEUTRAL": "HOLD",
        "REDUCE": "SELL",
        "AVOID": "SELL",
    }
    return replacements.get(normalized, normalized)


def parse_stock_name_from_markdown(markdown: str, ticker: str) -> str | None:
    patterns = [
        re.compile(rf"^#\s+Technical Analysis Report:\s+{re.escape(ticker)}\s+\(([^)]+)\)", flags=re.MULTILINE),
        re.compile(rf"^#\s+{re.escape(ticker)}\s+\(([^)]+)\)\s+Technical Analysis Report", flags=re.MULTILINE),
        re.compile(r"^\|\s*Company Name\s*\|\s*([^|]+?)\s*\|$", flags=re.MULTILINE),
        re.compile(rf"for\s+([A-Z][A-Za-z0-9&.,' \-]+?)\s+\((?:NASDAQ|NYSE|HKEX|NASDAQGS):?\s*{re.escape(ticker)}\)", flags=re.IGNORECASE),
    ]
    for pattern in patterns:
        match = pattern.search(markdown)
        if match:
            name = match.group(1).strip()
            if name:
                return name
    return None


def resolve_tradingagents_title(
    ticker: str,
    markdown: str,
    *,
    name_lookup: Callable[[str], str | None] | None = None,
) -> tuple[str, str]:
    stock_name = parse_stock_name_from_markdown(markdown, ticker)
    if stock_name:
        return f"{stock_name} - {ticker}", stock_name
    if name_lookup is not None:
        looked_up = name_lookup(ticker)
        if looked_up:
            return f"{looked_up} - {ticker}", looked_up
    return f"{ticker} - {ticker}", ticker


def lookup_stock_name_via_market_snapshot(ticker: str, *, host: str = "127.0.0.1", port: int = 11111) -> str | None:
    normalized = _normalize_moomoo_symbol(ticker)
    if not normalized:
        return None
    try:
        with MoomooOpenDQuoteClient(host=host, port=port) as client:
            row = client.get_underlying_snapshot(normalized)
    except Exception:
        return None
    for key in ("name", "stock_name", "security_name", "display_name"):
        name = str(get_first(row, key, default="") or "").strip()
        if name:
            return name
    return None


def _normalize_moomoo_symbol(ticker: str) -> str | None:
    text = ticker.strip().upper()
    if not text:
        return None
    if "." not in text:
        return f"US.{text}"
    if text.endswith(".HK"):
        return f"HK.{text[:-3]}"
    if text.startswith(("US.", "HK.")):
        return text
    return text


def build_tradingagents_entry_from_report(
    report_path: pathlib.Path,
    *,
    name_lookup: Callable[[str], str | None] | None = None,
) -> TradingAgentsEntry:
    ticker, run_time, folder_name = parse_tradingagents_report_directory(report_path)
    markdown = report_path.read_text(encoding="utf-8")
    title, stock_name = resolve_tradingagents_title(ticker, markdown, name_lookup=name_lookup)
    recommendation = extract_recommendation_from_markdown(markdown)
    return TradingAgentsEntry(
        title=title,
        date=run_time.date().isoformat(),
        run_key=run_time.strftime("%Y%m%d_%H%M%S"),
        run_path=str(report_path.parent),
        external_id=tradingagents_external_id(folder_name),
        ticker=ticker,
        stock_name=stock_name,
        recommendation=recommendation,
        report_markdown=markdown,
    )


def sync_tradingagents_report_directory(
    client: NotionClientProtocol,
    config: NotionSyncConfig,
    report_paths: Iterable[pathlib.Path],
    *,
    name_lookup: Callable[[str], str | None] | None = None,
) -> list[SyncResult]:
    payloads = [
        render_tradingagents_payload(build_tradingagents_entry_from_report(path, name_lookup=name_lookup))
        for path in report_paths
    ]
    return sync_payloads(client, config, payloads)


def _heading_block(kind: str, text: str) -> list[dict[str, Any]]:
    return [{"object": "block", "type": kind, kind: {"rich_text": _rich_text(text)}}]


def _paragraph_blocks(text: str) -> list[dict[str, Any]]:
    return [_paragraph_block(chunk) for chunk in _split_text_chunks(text)] or [_paragraph_block("")]


def _paragraph_block(text: str) -> dict[str, Any]:
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": _rich_text(text)}}


def _bulleted_list_blocks(items: Iterable[str]) -> list[dict[str, Any]]:
    return [_list_item_block("bulleted_list_item", item) for item in items if str(item).strip()]


def _list_item_block(kind: str, text: str) -> dict[str, Any]:
    return {"object": "block", "type": kind, kind: {"rich_text": _rich_text(text)}}


def _rich_text(value: Any) -> list[dict[str, Any]]:
    text = str(value)
    chunks = _split_text_chunks(text) or [""]
    return [{"type": "text", "text": {"content": chunk}} for chunk in chunks]


def _split_text_chunks(text: str, limit: int = MAX_NOTION_TEXT_LENGTH) -> list[str]:
    normalized = text.strip()
    if not normalized:
        return []
    chunks: list[str] = []
    remaining = normalized
    while len(remaining) > limit:
        split_at = remaining.rfind(" ", 0, limit)
        if split_at <= 0:
            split_at = limit
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def _table_block_from_dict_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        rows = [{"Value": ""}]
    headers = list(rows[0].keys())
    matrix = [headers] + [[_stringify_cell(row.get(header)) for header in headers] for row in rows]
    return _table_block_from_matrix(matrix)


def _table_block_from_matrix(matrix: list[list[str]]) -> dict[str, Any]:
    if not matrix:
        matrix = [["Value"], [""]]
    width = max(len(row) for row in matrix)
    rows = []
    for row in matrix:
        padded = list(row) + [""] * (width - len(row))
        rows.append(
            {
                "object": "block",
                "type": "table_row",
                "table_row": {"cells": [[{"type": "text", "text": {"content": cell[:MAX_NOTION_TEXT_LENGTH]}}] for cell in padded]},
            }
        )
    return {
        "object": "block",
        "type": "table",
        "table": {
            "table_width": width,
            "has_column_header": True,
            "has_row_header": False,
            "children": rows,
        },
    }


def _stringify_cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _format_shortlist_value(value: Any) -> str:
    if isinstance(value, float):
        if abs(value) <= 1:
            return f"{value:.4f}"
        return f"{value:.2f}"
    return _stringify_cell(value)


def _format_strike(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}"


def _format_decimal(value: Any) -> str:
    if value is None:
        return ""
    return f"{float(value):.4f}".rstrip("0").rstrip(".")


def _format_percent(value: Any) -> str:
    if value is None:
        return ""
    return f"{float(value):.1%}"


def _distribution_midpoint(distribution: Iterable[dict[str, Any]]) -> float:
    rows = list(distribution)
    if not rows:
        return 0.0
    values = [float(row.get("value", 0.0)) for row in rows]
    return sum(values) / len(values)
