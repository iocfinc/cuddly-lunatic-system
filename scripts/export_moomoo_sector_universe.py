#!/usr/bin/env python3
"""Export Moomoo HK/US plate taxonomy for supply-chain research."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from pathlib import Path
import sys
import time

from moomoo import Market, OpenQuoteContext, Plate, RET_OK

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quant_researcher_desk.industry_universe import (  # noqa: E402
    PlateRecord,
    build_domain_edges,
    build_industry_nodes,
)


MARKETS = {"HK": Market.HK, "US": Market.US}
PLATE_TYPES = {
    "INDUSTRY": Plate.INDUSTRY,
    "CONCEPT": Plate.CONCEPT,
    "REGION": Plate.REGION,
    "ALL": Plate.ALL,
}


def _records_from_frame(market: str, plate_type: str, data) -> list[PlateRecord]:
    records: list[PlateRecord] = []
    for i in range(len(data)):
        row = data.iloc[i] if hasattr(data, "iloc") else data[i]
        code = str(row.get("code", "")).strip()
        name = str(row.get("plate_name", row.get("stock_name", ""))).strip()
        if code and name:
            records.append(PlateRecord(market=market, plate_type=plate_type, code=code, name=name))
    return records


def fetch_plate_records(markets: list[str], plate_types: list[str], host: str, port: int) -> tuple[PlateRecord, ...]:
    ctx = OpenQuoteContext(host=host, port=port)
    try:
        records_by_code: dict[tuple[str, str], PlateRecord] = {}
        for market in markets:
            for plate_type in plate_types:
                ret, data = ctx.get_plate_list(MARKETS[market], PLATE_TYPES[plate_type])
                if ret != RET_OK and "high frequency" in str(data).lower():
                    time.sleep(31)
                    ret, data = ctx.get_plate_list(MARKETS[market], PLATE_TYPES[plate_type])
                if ret != RET_OK:
                    raise RuntimeError(f"get_plate_list failed for {market} {plate_type}: {data}")
                for record in _records_from_frame(market, plate_type, data):
                    key = (record.market, record.code)
                    existing = records_by_code.get(key)
                    if existing is None or existing.plate_type == "ALL":
                        records_by_code[key] = record
        records = tuple(records_by_code.values())
        return tuple(sorted(records, key=lambda record: (record.market, record.plate_type, record.name, record.code)))
    finally:
        ctx.close()


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def render_markdown(fetched_at: str, records: tuple[PlateRecord, ...]) -> str:
    nodes = build_industry_nodes(records)
    edges = build_domain_edges(nodes)
    by_market_type: dict[tuple[str, str], int] = {}
    by_gics_group: dict[tuple[str, str], int] = {}
    industry_nodes = [node for node in nodes if node.plate_type == "INDUSTRY"]
    priority_nodes = [node for node in nodes if node.research_priority == 1]
    for node in nodes:
        by_market_type[(node.market, node.plate_type)] = by_market_type.get((node.market, node.plate_type), 0) + 1
        by_gics_group[(node.gics_sector, node.gics_industry_group)] = by_gics_group.get((node.gics_sector, node.gics_industry_group), 0) + 1

    lines = [
        "# HK/US Sector and Industry Universe",
        "",
        f"Generated: `{fetched_at}`",
        "",
            "This is the working taxonomy for Quant Researcher Desk supply-chain research. It uses Moomoo OpenAPI plate lists as the live market taxonomy, then adds a local GICS research layer for sectors, industry groups, industries, value-chain roles, and graph edges.",
        "",
        "## Source Notes",
        "",
        "- Moomoo `get_plate_list(market, plate_class)` returns plate code, plate name, and plate ID for market sector lists: https://openapi.moomoo.com/moomoo-api-doc/en/quote/get-plate-list.html",
        "- Moomoo `get_plate_stock(plate_code)` can expand any plate into constituent stocks when a report needs a company list: https://openapi.moomoo.com/moomoo-api-doc/en/quote/get-plate-stock.html",
        "- GICS remains the global comparison frame: sectors, industry groups, industries, and sub-industries: https://www.msci.com/indexes/index-resources/gics",
        "- For Hong Kong listed-company context, HSICS is the exchange-facing industry classification lineage; HKEX adopted HSICS for all Hong Kong-listed companies: https://www.hkex.com.hk/News/News-Release/2007/071211news",
        "",
        "## Coverage Summary",
        "",
        "| Market | Plate type | Count |",
        "| --- | ---: | ---: |",
    ]
    for (market, plate_type), count in sorted(by_market_type.items()):
        lines.append(f"| {market} | {plate_type} | {count} |")

    lines.extend(
        [
            "",
            "## GICS Coverage",
            "",
            "| GICS sector | GICS industry group | Plates |",
            "| --- | --- | ---: |",
        ]
    )
    for (gics_sector, gics_group), count in sorted(by_gics_group.items(), key=lambda item: (item[0][0], item[0][1])):
        lines.append(f"| {gics_sector} | {gics_group} | {count} |")

    lines.extend(
        [
            "",
            "## Priority Industry Rotation Candidates",
            "",
            "These are representative live Moomoo industry plates grouped by GICS industry group. They should be the first expansion set for the 3-hour sector cron before lower-signal concept and region plates.",
            "",
            "| Market | GICS sector | GICS industry group | Drill-down industry | Representative plate | Role |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for node in priority_nodes:
        lines.append(f"| {node.market} | {node.gics_sector} | {node.gics_industry_group} | {node.gics_industry} | `{node.code}` {node.name} | {node.value_chain_role} |")

    lines.extend(
        [
            "",
            "## All Moomoo Industry Plates",
            "",
            "| Market | Code | Plate | GICS sector | GICS industry group | GICS industry | Role | Priority |",
            "| --- | --- | --- | --- | --- | --- | --- | ---: |",
        ]
    )
    for node in industry_nodes:
        lines.append(f"| {node.market} | `{node.code}` | {node.name} | {node.gics_sector} | {node.gics_industry_group} | {node.gics_industry} | {node.value_chain_role} | {node.research_priority} |")

    lines.extend(
        [
            "",
            "## Graph Model",
            "",
            "The graph starts with GICS industry-group nodes, Moomoo plate drill-downs, and heuristic edges. Use it as a research queue, not as a factual supplier contract map. Report writers should replace heuristic edges with sourced company-specific evidence when producing a brief.",
            "",
            "| File | Purpose |",
            "| --- | --- |",
            "| `data/sector-universe/moomoo_hk_us_plates.json` | Raw Moomoo plate taxonomy. |",
            "| `data/sector-universe/moomoo_hk_us_plates.csv` | Spreadsheet-friendly plate list. |",
            "| `data/sector-universe/value_chain_nodes.csv` | Graph nodes with domain and role labels. |",
            "| `data/sector-universe/value_chain_edges.csv` | Starter graph edges for upstream/midstream/downstream analysis. |",
            "| `data/sector-universe/value_chain_graph.mmd` | Mermaid graph preview for docs. |",
            "",
            f"Current graph size: `{len(nodes)}` nodes, `{len(edges)}` starter edges.",
            "",
            "## Research Use",
            "",
            "1. Pick a priority industry plate from this document.",
            "2. Expand constituents with Moomoo `get_plate_stock(plate_code)`.",
            "3. Assign companies to upstream, midstream, downstream, or enabler roles.",
            "4. Replace heuristic graph edges with sourced evidence: customer/supplier disclosure, revenue segment exposure, commodity input sensitivity, distribution channel, or regulatory linkage.",
            "5. Feed the selected market/industry into the scheduled sector brief rotation.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_mermaid(records: tuple[PlateRecord, ...]) -> str:
    nodes = build_industry_nodes(records)
    edges = build_domain_edges(nodes)
    by_id = {node.node_id: node for node in nodes}
    lines = ["flowchart LR"]
    for node in nodes:
        if node.research_priority <= 2:
            safe_id = _mermaid_id(node.node_id)
            label = f"{node.market} {node.name}\\n{node.value_chain_role}"
            lines.append(f'  {safe_id}["{label}"]')
    for edge in edges:
        source = by_id.get(edge.source_id)
        target = by_id.get(edge.target_id)
        if not source or not target or source.research_priority > 2 or target.research_priority > 2:
            continue
        lines.append(f"  {_mermaid_id(edge.source_id)} -->|{edge.relationship}| {_mermaid_id(edge.target_id)}")
    return "\n".join(lines) + "\n"


def _mermaid_id(value: str) -> str:
    return "n_" + "".join(char if char.isalnum() else "_" for char in value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="data/sector-universe")
    parser.add_argument("--docs-path", default="docs/sector-industry-universe.md")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=11111)
    args = parser.parse_args()

    fetched_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    records = fetch_plate_records(list(MARKETS), list(PLATE_TYPES), args.host, args.port)
    nodes = build_industry_nodes(records)
    edges = build_domain_edges(nodes)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_path = Path(args.docs_path)
    docs_path.parent.mkdir(parents=True, exist_ok=True)

    raw_payload = {
        "fetched_at": fetched_at,
        "source": "Moomoo OpenAPI get_plate_list",
        "markets": list(MARKETS),
        "plate_types": list(PLATE_TYPES),
        "records": [record.__dict__ for record in records],
    }
    (output_dir / "moomoo_hk_us_plates.json").write_text(json.dumps(raw_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    write_csv(output_dir / "moomoo_hk_us_plates.csv", [record.__dict__ for record in records], ["market", "plate_type", "code", "name", "source"])
    write_csv(output_dir / "value_chain_nodes.csv", [node.__dict__ for node in nodes], ["node_id", "market", "taxonomy", "plate_type", "code", "name", "domain", "value_chain_role", "research_priority", "gics_sector", "gics_industry_group", "gics_industry"])
    write_csv(output_dir / "value_chain_edges.csv", [edge.__dict__ for edge in edges], ["source_id", "target_id", "relationship", "rationale"])
    (output_dir / "value_chain_graph.mmd").write_text(render_mermaid(records), encoding="utf-8")
    docs_path.write_text(render_markdown(fetched_at, records), encoding="utf-8")

    print(f"exported {len(records)} plates, {len(nodes)} nodes, {len(edges)} edges")
    print(f"docs: {docs_path}")
    print(f"data: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
