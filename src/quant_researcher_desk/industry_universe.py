"""Industry and supply-chain taxonomy helpers for sector research."""

from __future__ import annotations

from dataclasses import dataclass
import csv
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class PlateRecord:
    market: str
    plate_type: str
    code: str
    name: str
    source: str = "moomoo_openapi"


@dataclass(frozen=True)
class IndustryNode:
    node_id: str
    market: str
    taxonomy: str
    plate_type: str
    code: str
    name: str
    domain: str
    value_chain_role: str
    research_priority: int
    gics_sector: str = "Cross-sector"
    gics_industry_group: str = "Cross-sector"
    gics_industry: str = "Cross-sector"


@dataclass(frozen=True)
class GicsClassification:
    sector: str
    industry_group: str
    industry: str


@dataclass(frozen=True)
class SupplyChainEdge:
    source_id: str
    target_id: str
    relationship: str
    rationale: str


DOMAIN_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Agriculture & Food", ("agricultur", "dairy", "food", "meat", "poultry", "livestock", "beverage", "catering", "supermarket", "tobacco")),
    ("Materials", ("metal", "mineral", "steel", "copper", "aluminum", "gold", "chemical", "paper", "timber", "forestry", "cement", "construction materials")),
    ("Energy & Utilities", ("oil", "gas", "coal", "energy", "renewable", "solar", "wind", "electric utilities", "water utilities", "nuclear", "storage")),
    ("Industrials & Manufacturing", ("machinery", "industrial", "manufactur", "equipment", "aerospace", "defense", "vehicle", "auto parts", "commercial vehicles", "engineering", "construction", "packaging")),
    ("Transportation & Logistics", ("transport", "logistics", "shipping", "ports", "railroad", "highway", "air cargo", "airlines", "public transport")),
    ("Consumer", ("retail", "apparel", "footwear", "jewelry", "watch", "consumer", "home", "furniture", "hotel", "resort", "casino", "gaming", "travel", "leisure", "sports", "toy", "personal care", "cosmetic")),
    ("Healthcare", ("medical", "pharma", "biotech", "health", "medicine", "therapeutic", "diagnostic")),
    ("Financials", ("bank", "insurance", "credit", "financial", "brokerage", "asset management", "payment", "reit")),
    ("Technology & Telecom", ("semiconductor", "software", "internet", "telecom", "cloud", "computer", "electronic", "application", "digital", "saas", "ai", "interactive media")),
    ("Real Estate & Infrastructure", ("real estate", "property", "infrastructure", "building materials")),
    ("Media & Entertainment", ("media", "advertising", "broadcast", "publishing", "entertainment", "games")),
    ("Environmental Services", ("environmental", "waste", "water")),
)

GICS_RULES: tuple[tuple[tuple[str, ...], GicsClassification], ...] = (
    (
        ("semiconductor",),
        GicsClassification("Information Technology", "Semiconductors & Semiconductor Equipment", "Semiconductors & Semiconductor Equipment"),
    ),
    (
        ("software", "saas", "cloud", "application", "digital solution", "internet services"),
        GicsClassification("Information Technology", "Software & Services", "Software"),
    ),
    (
        ("internet content", "interactive media", "games", "gaming", "media", "advertising", "broadcast", "publishing", "entertainment"),
        GicsClassification("Communication Services", "Media & Entertainment", "Interactive Media & Services"),
    ),
    (
        ("telecom",),
        GicsClassification("Communication Services", "Telecommunication Services", "Diversified Telecommunication Services"),
    ),
    (
        ("bank",),
        GicsClassification("Financials", "Banks", "Banks"),
    ),
    (
        ("insurance",),
        GicsClassification("Financials", "Insurance", "Insurance"),
    ),
    (
        ("brokerage", "asset management", "credit", "payment", "financial"),
        GicsClassification("Financials", "Financial Services", "Capital Markets"),
    ),
    (
        ("aerospace", "defense"),
        GicsClassification("Industrials", "Capital Goods", "Aerospace & Defense"),
    ),
    (
        ("transport", "logistics", "shipping", "ports", "railroad", "highway", "air cargo", "airlines", "airports", "marine"),
        GicsClassification("Industrials", "Transportation", "Transportation Infrastructure"),
    ),
    (
        ("machinery", "industrial", "manufactur", "equipment", "engineering", "construction", "packaging"),
        GicsClassification("Industrials", "Capital Goods", "Machinery"),
    ),
    (
        ("electric utilities", "water utilities", "gas utilities", "utilities", "renewable", "solar", "wind", "nuclear"),
        GicsClassification("Utilities", "Utilities", "Utilities"),
    ),
    (
        ("oil", "gas", "coal", "energy", "drilling", "refining"),
        GicsClassification("Energy", "Energy", "Oil, Gas & Consumable Fuels"),
    ),
    (
        ("pharma", "biotech", "therapeutic", "medicine"),
        GicsClassification("Health Care", "Pharmaceuticals, Biotechnology & Life Sciences", "Pharmaceuticals"),
    ),
    (
        ("medical", "health", "diagnostic"),
        GicsClassification("Health Care", "Health Care Equipment & Services", "Health Care Equipment & Supplies"),
    ),
    (
        ("reit", "real estate", "property"),
        GicsClassification("Real Estate", "Equity Real Estate Investment Trusts", "Retail REITs"),
    ),
    (
        ("hotel", "resort", "casino", "catering", "travel", "leisure", "sports", "recreation"),
        GicsClassification("Consumer Discretionary", "Consumer Services", "Hotels, Restaurants & Leisure"),
    ),
    (
        ("apparel", "footwear", "home improvement", "specialty retail", "auto retail", "jewelry", "watch", "consumer electronics"),
        GicsClassification("Consumer Discretionary", "Consumer Discretionary Distribution & Retail", "Specialty Retail"),
    ),
    (
        ("internet retail", "online retailers", "supermarket", "retail"),
        GicsClassification("Consumer Staples", "Consumer Staples Distribution & Retail", "Consumer Staples Distribution & Retail"),
    ),
    (
        ("beverage", "dairy", "food", "meat", "poultry", "tobacco", "packaged"),
        GicsClassification("Consumer Staples", "Food, Beverage & Tobacco", "Food Products"),
    ),
    (
        ("agricultur", "livestock feed"),
        GicsClassification("Materials", "Materials", "Chemicals"),
    ),
    (
        ("metal", "mineral", "steel", "copper", "aluminum", "gold", "chemical", "paper", "timber", "forestry", "cement", "construction materials"),
        GicsClassification("Materials", "Materials", "Metals & Mining"),
    ),
)

UPSTREAM_KEYWORDS = (
    "agricultur",
    "inputs",
    "forestry",
    "timber",
    "mineral",
    "metal",
    "coal",
    "oil & gas producers",
    "gold",
    "copper",
    "aluminum",
    "chemical",
    "livestock feed",
    "paper",
)
MIDSTREAM_KEYWORDS = (
    "manufactur",
    "equipment",
    "machinery",
    "components",
    "semiconductor",
    "packaging",
    "construction",
    "engineering",
    "pharmaceuticals",
    "biotechnology",
    "software",
    "internet services",
    "logistics",
    "transport",
    "utilities",
    "food additives",
    "packaged food",
)
DOWNSTREAM_KEYWORDS = (
    "retail",
    "catering",
    "hotel",
    "resort",
    "casino",
    "gaming",
    "travel",
    "consumer",
    "home appliances",
    "jewelry",
    "apparel",
    "footwear",
    "beverage",
    "supermarket",
    "online retailers",
    "interactive media",
)
ENABLER_KEYWORDS = (
    "bank",
    "insurance",
    "credit",
    "brokerage",
    "asset management",
    "payment",
    "advertising",
    "support services",
    "digital solution",
)


def classify_domain(name: str) -> str:
    normalized = name.lower()
    for domain, keywords in DOMAIN_RULES:
        if any(keyword in normalized for keyword in keywords):
            return domain
    return "Other / Cross-sector"


def classify_gics(name: str, domain: str = "") -> GicsClassification:
    normalized = name.lower()
    for keywords, classification in GICS_RULES:
        if any(keyword in normalized for keyword in keywords):
            return classification
    if domain == "Technology & Telecom":
        return GicsClassification("Information Technology", "Software & Services", "IT Services")
    if domain == "Financials":
        return GicsClassification("Financials", "Financial Services", "Financial Services")
    if domain == "Consumer":
        return GicsClassification("Consumer Discretionary", "Consumer Discretionary Distribution & Retail", "Distributors")
    return GicsClassification("Cross-sector", "Cross-sector", "Cross-sector")


def classify_value_chain_role(name: str) -> str:
    normalized = name.lower()
    if any(keyword in normalized for keyword in UPSTREAM_KEYWORDS):
        return "upstream"
    if any(keyword in normalized for keyword in DOWNSTREAM_KEYWORDS):
        return "downstream"
    if any(keyword in normalized for keyword in MIDSTREAM_KEYWORDS):
        return "midstream"
    if any(keyword in normalized for keyword in ENABLER_KEYWORDS):
        return "enabler"
    return "cross_chain"


def research_priority(plate: PlateRecord) -> int:
    domain = classify_domain(plate.name)
    role = classify_value_chain_role(plate.name)
    if plate.plate_type == "INDUSTRY" and role in {"upstream", "midstream", "downstream"}:
        return 1
    if plate.plate_type == "INDUSTRY":
        return 2
    if plate.plate_type == "CONCEPT" and domain != "Other / Cross-sector":
        return 3
    return 4


def build_industry_nodes(records: Iterable[PlateRecord]) -> tuple[IndustryNode, ...]:
    nodes = []
    for record in records:
        market = record.market.upper()
        plate_type = record.plate_type.upper()
        node_id = f"{market}:{plate_type}:{record.code}"
        domain = classify_domain(record.name)
        gics = classify_gics(record.name, domain)
        nodes.append(
            IndustryNode(
                node_id=node_id,
                market=market,
                taxonomy="GICS overlay / Moomoo Plate",
                plate_type=plate_type,
                code=record.code,
                name=record.name,
                domain=domain,
                value_chain_role=classify_value_chain_role(record.name),
                research_priority=research_priority(record),
                gics_sector=gics.sector,
                gics_industry_group=gics.industry_group,
                gics_industry=gics.industry,
            )
        )
    return tuple(
        sorted(
            nodes,
            key=lambda node: (
                node.market,
                node.gics_sector,
                node.gics_industry_group,
                node.plate_type,
                node.research_priority,
                node.name,
            ),
        )
    )


def build_domain_edges(nodes: Iterable[IndustryNode]) -> tuple[SupplyChainEdge, ...]:
    by_market_domain_role: dict[tuple[str, str, str], list[IndustryNode]] = {}
    for node in nodes:
        by_market_domain_role.setdefault((node.market, node.domain, node.value_chain_role), []).append(node)

    edges: list[SupplyChainEdge] = []
    for (market, domain, role), source_nodes in by_market_domain_role.items():
        if role != "upstream":
            continue
        midstream_nodes = by_market_domain_role.get((market, domain, "midstream"), [])
        downstream_nodes = by_market_domain_role.get((market, domain, "downstream"), [])
        for source in source_nodes:
            for target in midstream_nodes[:8]:
                edges.append(
                    SupplyChainEdge(
                        source_id=source.node_id,
                        target_id=target.node_id,
                        relationship="supplies_or_inputs_to",
                        rationale=f"{source.name} is a likely input layer for {target.name} inside {domain}.",
                    )
                )
        for source in midstream_nodes[:8]:
            for target in downstream_nodes[:8]:
                edges.append(
                    SupplyChainEdge(
                        source_id=source.node_id,
                        target_id=target.node_id,
                        relationship="enables_or_distributes_to",
                        rationale=f"{source.name} is a likely operating or conversion layer before {target.name} demand.",
                    )
                )
    return tuple(sorted(edges, key=lambda edge: (edge.source_id, edge.target_id, edge.relationship)))


def load_industry_nodes_csv(path: str | Path) -> tuple[IndustryNode, ...]:
    rows: list[IndustryNode] = []
    with Path(path).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            domain = row["domain"]
            gics = classify_gics(row["name"], domain)
            rows.append(
                IndustryNode(
                    node_id=row["node_id"],
                    market=row["market"],
                    taxonomy=row["taxonomy"],
                    plate_type=row["plate_type"],
                    code=row["code"],
                    name=row["name"],
                    domain=row["domain"],
                    value_chain_role=row["value_chain_role"],
                    research_priority=int(row["research_priority"]),
                    gics_sector=row.get("gics_sector") or gics.sector,
                    gics_industry_group=row.get("gics_industry_group") or gics.industry_group,
                    gics_industry=row.get("gics_industry") or gics.industry,
                )
            )
    return tuple(rows)


def load_supply_chain_edges_csv(path: str | Path) -> tuple[SupplyChainEdge, ...]:
    rows: list[SupplyChainEdge] = []
    with Path(path).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            rows.append(
                SupplyChainEdge(
                    source_id=row["source_id"],
                    target_id=row["target_id"],
                    relationship=row["relationship"],
                    rationale=row["rationale"],
                )
            )
    return tuple(rows)


def priority_rotation_nodes(nodes: Iterable[IndustryNode]) -> tuple[IndustryNode, ...]:
    role_rank = {"upstream": 0, "midstream": 1, "downstream": 2}
    representatives: dict[tuple[str, str], IndustryNode] = {}
    for node in sorted(
        (
            node
            for node in nodes
            if node.plate_type == "INDUSTRY"
            and node.gics_industry_group != "Cross-sector"
            and node.research_priority <= 2
            and node.value_chain_role in {"upstream", "midstream", "downstream", "enabler", "cross_chain"}
        ),
        key=lambda node: (
            node.market,
            node.gics_sector,
            node.gics_industry_group,
            node.research_priority,
            role_rank.get(node.value_chain_role, 9),
            node.name,
        ),
    ):
        key = (node.market, node.gics_industry_group)
        representatives.setdefault(key, node)
    return tuple(representatives.values())
