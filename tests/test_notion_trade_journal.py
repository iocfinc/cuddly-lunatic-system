from __future__ import annotations

import copy
import dataclasses
import datetime as dt
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quant_researcher_desk.notion_trade_journal import (
    NotionEntryPayload,
    NotionSchemaError,
    NotionSyncConfig,
    build_tradingagents_entry_from_report,
    build_weekly_sync_payloads,
    discover_tradingagents_reports,
    extract_recommendation_from_markdown,
    markdown_to_notion_blocks,
    parse_tradingagents_report_directory,
    render_tradingagents_payload,
    resolve_tradingagents_title,
    sync_payloads,
    tradingagents_external_id,
    validate_trade_journal_schema,
    weekly_run_external_id,
    weekly_tearsheet_external_id,
)
from quant_researcher_desk.options_research import FixtureOptionsResearchProvider
from quant_researcher_desk.weekly_options_packet import build_weekly_options_packet
from quant_researcher_desk.weekly_options_screener import FixtureWeeklyScreenProvider, WeeklyScreenRequest, build_weekly_options_screen


TRADE_JOURNAL_SCHEMA = {
    "Name": {"type": "title"},
    "Date": {"type": "date"},
    "Tags": {"type": "multi_select"},
    "Entry Type": {"type": "select"},
    "Source": {"type": "select"},
    "Ticker": {"type": "rich_text"},
    "Option Side": {"type": "select"},
    "Recommendation": {"type": "select"},
    "Run Key": {"type": "rich_text"},
    "Run Path": {"type": "rich_text"},
    "External ID": {"type": "rich_text"},
}


class _FakeDatabases:
    def __init__(self, client: "_FakeNotionClient") -> None:
        self._client = client

    def retrieve(self, database_id: str) -> dict[str, object]:
        assert database_id == self._client.database_id
        return {"properties": copy.deepcopy(self._client.schema)}

    def query(self, database_id: str, filter: dict[str, object], page_size: int = 100) -> dict[str, object]:
        assert database_id == self._client.database_id
        property_name = str(filter["property"])
        _, condition = next((key, value) for key, value in filter.items() if key != "property")
        target = str(condition["equals"])  # type: ignore[index]
        matches = []
        for page in self._client.pages_store.values():
            value = self._client.property_text(page["properties"].get(property_name, {}))
            if value == target:
                matches.append(copy.deepcopy(page))
        return {"results": matches[:page_size]}


class _FakePages:
    def __init__(self, client: "_FakeNotionClient") -> None:
        self._client = client

    def create(self, parent: dict[str, object], properties: dict[str, object], children: list[dict[str, object]]) -> dict[str, object]:
        assert parent["database_id"] == self._client.database_id
        page_id = f"page-{self._client.next_page_id}"
        self._client.next_page_id += 1
        page = {
            "id": page_id,
            "properties": copy.deepcopy(properties),
            "children": self._client.with_block_ids(children),
        }
        self._client.pages_store[page_id] = page
        return copy.deepcopy(page)

    def update(self, page_id: str, properties: dict[str, object]) -> dict[str, object]:
        page = self._client.pages_store[page_id]
        page["properties"] = copy.deepcopy(properties)
        return copy.deepcopy(page)


class _FakeBlocksChildren:
    def __init__(self, client: "_FakeNotionClient") -> None:
        self._client = client

    def list(self, block_id: str, start_cursor: str | None = None) -> dict[str, object]:
        if block_id in self._client.template_children:
            children = self._client.template_children[block_id]
        else:
            children = self._client.pages_store[block_id]["children"]
        return {
            "results": copy.deepcopy(children),
            "has_more": False,
            "next_cursor": None,
        }

    def append(self, block_id: str, children: list[dict[str, object]]) -> dict[str, object]:
        hydrated = self._client.with_block_ids(children)
        self._client.pages_store[block_id]["children"].extend(hydrated)
        return {"results": copy.deepcopy(hydrated)}


class _FakeBlocks:
    def __init__(self, client: "_FakeNotionClient") -> None:
        self._client = client
        self.children = _FakeBlocksChildren(client)

    def delete(self, block_id: str) -> None:
        for page in self._client.pages_store.values():
            page["children"] = [child for child in page["children"] if child.get("id") != block_id]


class _FakeNotionClient:
    def __init__(self, *, schema: dict[str, dict[str, str]], template_children: list[dict[str, object]] | None = None) -> None:
        self.database_id = "trade-journal-db"
        self.schema = copy.deepcopy(schema)
        self.pages_store: dict[str, dict[str, object]] = {}
        self.next_page_id = 1
        self.next_block_id = 1
        self.template_children = {"template-page": self.with_block_ids(template_children or [])}
        self.databases = _FakeDatabases(self)
        self.pages = _FakePages(self)
        self.blocks = _FakeBlocks(self)

    def property_text(self, property_payload: dict[str, object]) -> str:
        if "rich_text" in property_payload:
            return "".join(str(item["text"]["content"]) for item in property_payload["rich_text"])  # type: ignore[index]
        if "title" in property_payload:
            return "".join(str(item["text"]["content"]) for item in property_payload["title"])  # type: ignore[index]
        return ""

    def with_block_ids(self, blocks: list[dict[str, object]]) -> list[dict[str, object]]:
        hydrated: list[dict[str, object]] = []
        for block in copy.deepcopy(blocks):
            if "id" not in block:
                block["id"] = f"block-{self.next_block_id}"
                self.next_block_id += 1
            block_type = str(block.get("type", ""))
            payload = block.get(block_type)
            if isinstance(payload, dict) and isinstance(payload.get("children"), list):
                payload["children"] = self.with_block_ids(payload["children"])
            hydrated.append(block)
        return hydrated


def _sync_config(*, dry_run: bool = False) -> NotionSyncConfig:
    return NotionSyncConfig(
        enabled=True,
        dry_run=dry_run,
        api_token="test-token",
        trade_journal_database_id="trade-journal-db",
        template_page_id="template-page",
    )


def _build_packet():
    now = dt.datetime(2026, 5, 26, 9, 30, tzinfo=dt.timezone.utc)
    weekly = build_weekly_options_screen(
        FixtureWeeklyScreenProvider(anchor_date=now.date()),
        WeeklyScreenRequest(market="US", top_n=2, historical_volatility=0.22),
        now=now,
    )
    return build_weekly_options_packet(
        weekly,
        FixtureOptionsResearchProvider(anchor_date=now.date()),
        now=now,
    )


def test_external_id_helpers_are_stable() -> None:
    assert weekly_run_external_id("20260526_093000") == "weekly-run:20260526_093000"
    assert weekly_tearsheet_external_id("20260526_093000", "US.AAPL260529C210000") == (
        "weekly-tearsheet:20260526_093000:US.AAPL260529C210000"
    )
    assert tradingagents_external_id("KLAC_20260517_212617") == "tradingagents:KLAC_20260517_212617"


def test_render_weekly_run_payload_sets_title_properties_and_block_order() -> None:
    packet = _build_packet()
    entry = build_weekly_sync_payloads(packet, run_path=pathlib.Path("/tmp/weekly"), attachment_path=pathlib.Path("/tmp/weekly/packet.pdf"))[0]

    assert entry.title == "Weekly Options Screen - 2026-05-26"
    assert entry.entry_type == "Weekly Run"
    assert entry.source == "naval-analyst"
    assert entry.external_id == "weekly-run:20260526_093000"
    assert entry.blocks[0]["type"] == "heading_2"
    assert entry.blocks[0]["heading_2"]["rich_text"][0]["text"]["content"] == "Stock-First Methodology"


def test_render_weekly_tearsheet_payload_keeps_stock_context_first_and_option_side() -> None:
    packet = _build_packet()
    payload = build_weekly_sync_payloads(packet, run_path=pathlib.Path("/tmp/weekly"))[1]

    assert payload.entry_type == "Weekly Tear Sheet"
    assert payload.option_side == packet.weekly_result.ranked_options[0].side
    assert payload.ticker == packet.weekly_result.ranked_options[0].symbol
    assert payload.blocks[0]["heading_2"]["rich_text"][0]["text"]["content"] == "Stock Context"


def test_parse_tradingagents_report_directory_extracts_ticker_and_run_date() -> None:
    report_path = pathlib.Path("/tmp/reports/KLAC_20260517_212617/complete_report.md")
    ticker, run_time, folder_name = parse_tradingagents_report_directory(report_path)

    assert ticker == "KLAC"
    assert run_time.date().isoformat() == "2026-05-17"
    assert folder_name == "KLAC_20260517_212617"


def test_extract_recommendation_prefers_portfolio_manager_section() -> None:
    markdown = """
FINAL TRANSACTION PROPOSAL: **SELL**

## III. Trading Team Plan
FINAL TRANSACTION PROPOSAL: **HOLD**

## V. Portfolio Manager Decision
- For all market participants with **<6 month trading horizons**: **Buy**
""".strip()

    assert extract_recommendation_from_markdown(markdown) == "BUY"


def test_title_resolution_prefers_report_parse_then_lookup_then_fallback() -> None:
    parsed_title, parsed_name = resolve_tradingagents_title(
        "KLAC",
        "# Technical Analysis Report: KLAC (KLA Corporation)\n",
        name_lookup=lambda _: "Ignored Lookup",
    )
    lookup_title, lookup_name = resolve_tradingagents_title(
        "XYZ",
        "# Trading Analysis Report: XYZ\n",
        name_lookup=lambda _: "Lookup Name",
    )
    fallback_title, fallback_name = resolve_tradingagents_title("ABC", "# Trading Analysis Report: ABC\n", name_lookup=lambda _: None)

    assert (parsed_title, parsed_name) == ("KLA Corporation - KLAC", "KLA Corporation")
    assert (lookup_title, lookup_name) == ("Lookup Name - XYZ", "Lookup Name")
    assert (fallback_title, fallback_name) == ("ABC - ABC", "ABC")


def test_markdown_to_notion_blocks_preserves_headings_tables_lists_and_plain_text() -> None:
    markdown = """
# Heading

Paragraph text with **unsupported inline markdown**.

| Col A | Col B |
| --- | --- |
| 1 | 2 |

- First
- Second

~~~raw~~~
""".strip()

    blocks = markdown_to_notion_blocks(markdown)

    assert [block["type"] for block in blocks[:4]] == ["heading_1", "paragraph", "table", "bulleted_list_item"]
    assert blocks[2]["table"]["table_width"] == 2
    assert blocks[-1]["type"] == "paragraph"


def test_sync_payloads_upserts_by_external_id_and_replaces_page_content() -> None:
    client = _FakeNotionClient(
        schema=TRADE_JOURNAL_SCHEMA,
        template_children=[{"id": "template-1", "object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": "Template"}}]}}],
    )
    payload = NotionEntryPayload(
        title="Weekly Options Screen - 2026-05-26",
        date="2026-05-26",
        entry_type="Weekly Run",
        source="naval-analyst",
        external_id="weekly-run:20260526_093000",
        run_key="20260526_093000",
        run_path="/tmp/weekly",
        blocks=(
            {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [{"type": "text", "text": {"content": "Version One"}}]}},
        ),
    )

    first_results = sync_payloads(client, _sync_config(), [payload])
    updated_payload = dataclasses.replace(
        payload,
        blocks=(
            {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [{"type": "text", "text": {"content": "Version Two"}}]}},
        ),
    )
    second_results = sync_payloads(client, _sync_config(), [updated_payload])

    assert first_results[0].action == "created"
    assert second_results[0].action == "updated"
    assert len(client.pages_store) == 1
    children = next(iter(client.pages_store.values()))["children"]
    assert children[0]["paragraph"]["rich_text"][0]["text"]["content"] == "Template"
    assert children[1]["heading_2"]["rich_text"][0]["text"]["content"] == "Version Two"


def test_weekly_sync_with_mocked_notion_client_creates_run_and_tearsheet_pages() -> None:
    client = _FakeNotionClient(schema=TRADE_JOURNAL_SCHEMA)
    packet = _build_packet()

    results = sync_payloads(
        client,
        dataclasses.replace(_sync_config(), template_page_id=None),
        build_weekly_sync_payloads(packet, run_path=pathlib.Path("/tmp/weekly"), attachment_path=pathlib.Path("/tmp/weekly/packet.pdf")),
    )

    assert len(results) == 1 + len(packet.tearsheets)
    assert all(result.action == "created" for result in results)
    assert len(client.pages_store) == 1 + len(packet.tearsheets)


def test_tradingagents_directory_sync_is_idempotent(tmp_path: pathlib.Path) -> None:
    client = _FakeNotionClient(schema=TRADE_JOURNAL_SCHEMA)
    config = dataclasses.replace(_sync_config(), template_page_id=None)
    reports_root = tmp_path / "reports"
    report_paths = [
        reports_root / "KLAC_20260517_212617" / "complete_report.md",
        reports_root / "GRAB_20260518_123005" / "complete_report.md",
    ]
    report_paths[0].parent.mkdir(parents=True)
    report_paths[1].parent.mkdir(parents=True)
    report_paths[0].write_text(
        """
# Technical Analysis Report: KLAC (KLA Corporation)

## V. Portfolio Manager Decision
**Recommendation:** **Underweight**
""".strip(),
        encoding="utf-8",
    )
    report_paths[1].write_text(
        """
# GRAB (Grab Holdings Limited) Technical Analysis Report

FINAL TRANSACTION PROPOSAL: **SELL**

## V. Portfolio Manager Decision
- For all market participants with **<6 month trading horizons**: **Buy**
""".strip(),
        encoding="utf-8",
    )

    discovered = discover_tradingagents_reports(reports_root)
    payloads = [render_tradingagents_payload(build_tradingagents_entry_from_report(path)) for path in discovered]

    first_results = sync_payloads(client, config, payloads)
    second_results = sync_payloads(client, config, payloads)

    assert len(first_results) == 2
    assert len(second_results) == 2
    assert all(result.action == "created" for result in first_results)
    assert all(result.action == "updated" for result in second_results)
    assert len(client.pages_store) == 2
    titles = sorted(page["properties"]["Name"]["title"][0]["text"]["content"] for page in client.pages_store.values())
    assert titles == ["Grab Holdings Limited - GRAB", "KLA Corporation - KLAC"]


def test_build_tradingagents_entry_uses_lookup_then_fallback(tmp_path: pathlib.Path) -> None:
    report_path = tmp_path / "reports" / "XYZ_20260519_120000" / "complete_report.md"
    report_path.parent.mkdir(parents=True)
    report_path.write_text("# Trading Analysis Report: XYZ\n", encoding="utf-8")

    lookup_entry = build_tradingagents_entry_from_report(report_path, name_lookup=lambda _: "Lookup Co")
    fallback_entry = build_tradingagents_entry_from_report(report_path, name_lookup=lambda _: None)

    assert lookup_entry.title == "Lookup Co - XYZ"
    assert fallback_entry.title == "XYZ - XYZ"


def test_validate_trade_journal_schema_fails_fast_for_missing_properties() -> None:
    client = _FakeNotionClient(schema={"Name": {"type": "title"}, "Date": {"type": "date"}})

    with pytest.raises(NotionSchemaError, match="missing properties"):
        validate_trade_journal_schema(client, client.database_id)
