"""Hong Kong Finance breadth-first power map reports."""

from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
from typing import Protocol


@dataclass(frozen=True)
class FinancePowerMapNode:
    symbol: str
    name: str
    market: str
    layer: str
    tradingview_sector: str
    tradingview_industry: str
    role: str
    catalyst: str
    risk: str
    why_it_matters: str


@dataclass(frozen=True)
class FinancePowerMapEdge:
    source_symbol: str
    target_symbol: str
    relationship: str
    evidence: str
    risk_note: str = ""


@dataclass(frozen=True)
class FinancePowerMapRequest:
    market: str = "HK"
    sector: str = "finance"


@dataclass(frozen=True)
class FinancePowerMapReport:
    request: FinancePowerMapRequest
    upstream: tuple[FinancePowerMapNode, ...]
    midstream: tuple[FinancePowerMapNode, ...]
    downstream: tuple[FinancePowerMapNode, ...]
    edges: tuple[FinancePowerMapEdge, ...]
    thesis: str
    learning_corner: str
    telegram_tldr: str
    marketing_copy: str
    tradingview_sector: str
    tradingview_industries: tuple[str, ...]
    generated_at: dt.datetime


class FinancePowerMapProvider(Protocol):
    def get_nodes(self, market: str, sector: str) -> list[FinancePowerMapNode]:
        ...

    def get_edges(self, market: str, sector: str) -> list[FinancePowerMapEdge]:
        ...


class FinancePowerMapError(ValueError):
    """Raised when the finance power-map report cannot be built."""


class FixtureHKFinancePowerMapProvider:
    """Deterministic local provider for the first HK Finance trial."""

    def get_nodes(self, market: str, sector: str) -> list[FinancePowerMapNode]:
        return list(_FIXTURE_NODES.get(_fixture_key(market, sector), ()))

    def get_edges(self, market: str, sector: str) -> list[FinancePowerMapEdge]:
        return list(_FIXTURE_EDGES.get(_fixture_key(market, sector), ()))


def build_hk_finance_power_map_report(
    request: FinancePowerMapRequest | None = None,
    provider: FinancePowerMapProvider | None = None,
) -> FinancePowerMapReport:
    provider = provider or FixtureHKFinancePowerMapProvider()
    request = request or FinancePowerMapRequest()
    normalized = _normalize_request(request)
    nodes = provider.get_nodes(normalized.market, normalized.sector)
    edges = provider.get_edges(normalized.market, normalized.sector)

    selected_nodes = tuple(sorted((_normalize_node(node) for node in nodes), key=_node_sort_key))
    if not selected_nodes:
        raise FinancePowerMapError(f"No fixture data found for {normalized.market} {normalized.sector}.")

    grouped = _group_nodes(selected_nodes)
    visible_nodes = tuple(node for layer in ("upstream", "midstream", "downstream") for node in grouped[layer])
    selected_symbols = {node.symbol for node in visible_nodes}
    selected_edges = tuple(
        sorted(
            (
                edge
                for edge in edges
                if edge.source_symbol in selected_symbols and edge.target_symbol in selected_symbols
            ),
            key=lambda edge: (edge.source_symbol, edge.target_symbol, edge.relationship),
        )
    )
    thesis = _build_thesis(normalized, grouped, selected_edges)
    learning_corner = _build_learning_corner()
    telegram_tldr = _build_telegram_tldr(normalized, grouped, selected_edges)
    marketing_copy = _build_marketing_copy(normalized, grouped)
    tradingview_industries = tuple(dict.fromkeys(node.tradingview_industry for node in selected_nodes))

    return FinancePowerMapReport(
        request=normalized,
        upstream=grouped["upstream"],
        midstream=grouped["midstream"],
        downstream=grouped["downstream"],
        edges=selected_edges,
        thesis=thesis,
        learning_corner=learning_corner,
        telegram_tldr=telegram_tldr,
        marketing_copy=marketing_copy,
        tradingview_sector="Financials",
        tradingview_industries=tradingview_industries,
        generated_at=dt.datetime.now(),
    )


def finance_power_map_sections(report: FinancePowerMapReport) -> list[dict[str, object]]:
    return [
        {
            "title": "Power Thesis",
            "content": report.thesis,
        },
        {
            "title": "Breadth-First Map",
            "summary": "The graph is ordered left to right: upstream capital and risk pools, midstream intermediation, then downstream customer-facing rails and deployment channels.",
            "relationship_map": _relationship_map(report),
        },
        {
            "title": "Sector Matrix",
            "summary": "TradingView HK finance plate reference with role, catalyst, and risk notes for each node.",
            "table": _node_rows(report),
        },
        {
            "title": "Relationship Edges",
            "summary": "These are reference links that show how balance-sheet stress or capital flow can travel across the stack.",
            "table": _edge_rows(report),
        },
        {
            "title": "Learning Corner",
            "items": [report.learning_corner],
        },
        {
            "title": "Telegram TLDR",
            "content": report.telegram_tldr,
        },
    ]


def format_hk_finance_telegram_html(report: FinancePowerMapReport, include_image: bool = True) -> str:
    node_count = len(report.upstream) + len(report.midstream) + len(report.downstream)
    tldr_lines = [line for line in report.telegram_tldr.splitlines() if line.strip()]
    return "\n".join(
        [
            "<b>HK Finance Breadth-First Power Map</b>",
            f"Scope: <code>{report.request.market} {report.request.sector.title()}</code> | Layers: <code>3</code> | Nodes: <code>{node_count}</code> | Edges: <code>{len(report.edges)}</code>",
            "",
            "\n".join(tldr_lines),
            "",
            "PDF attached." if include_image is False else "PDF attached.",
            "Research only, not a trading instruction.",
        ]
    )


def _normalize_request(request: FinancePowerMapRequest) -> FinancePowerMapRequest:
    market = request.market.strip().upper()
    sector = request.sector.strip().lower().replace("_", "-")
    if not market:
        raise FinancePowerMapError("Market is required.")
    if market != "HK":
        raise FinancePowerMapError("Only HK market coverage is implemented for the first trial sector.")
    if sector != "finance":
        raise FinancePowerMapError("Only HK finance is implemented for the first trial sector.")
    return FinancePowerMapRequest(market=market, sector="finance")


def _normalize_node(node: FinancePowerMapNode) -> FinancePowerMapNode:
    return FinancePowerMapNode(
        symbol=node.symbol.strip().upper(),
        name=node.name.strip(),
        market=node.market.strip().upper(),
        layer=node.layer.strip().lower(),
        tradingview_sector=node.tradingview_sector.strip(),
        tradingview_industry=node.tradingview_industry.strip(),
        role=node.role.strip(),
        catalyst=node.catalyst.strip(),
        risk=node.risk.strip(),
        why_it_matters=node.why_it_matters.strip(),
    )


def _node_sort_key(node: FinancePowerMapNode) -> tuple[int, str, str]:
    layer_order = {"upstream": 0, "midstream": 1, "downstream": 2}
    return (layer_order.get(node.layer, 99), node.tradingview_industry, node.symbol)


def _group_nodes(nodes: tuple[FinancePowerMapNode, ...]) -> dict[str, tuple[FinancePowerMapNode, ...]]:
    grouped: dict[str, tuple[FinancePowerMapNode, ...]] = {}
    for layer in ("upstream", "midstream", "downstream"):
        grouped[layer] = tuple(node for node in nodes if node.layer == layer)
    return grouped


def _build_thesis(
    request: FinancePowerMapRequest,
    grouped: dict[str, tuple[FinancePowerMapNode, ...]],
    edges: tuple[FinancePowerMapEdge, ...],
) -> str:
    total = sum(len(grouped[layer]) for layer in ("upstream", "midstream", "downstream"))
    upstream = ", ".join(f"{node.symbol} ({node.name})" for node in grouped["upstream"]) or "none"
    midstream = ", ".join(f"{node.symbol} ({node.name})" for node in grouped["midstream"]) or "none"
    downstream = ", ".join(f"{node.symbol} ({node.name})" for node in grouped["downstream"]) or "none"
    relationships = "; ".join(f"{edge.source_symbol} to {edge.target_symbol}" for edge in edges) if edges else "none"
    return (
        f"The {request.market} {request.sector.title()} power map is a breadth-first reference network, not a trading signal. "
        f"TradingView HK financial plates break cleanly into funding and risk pools upstream, "
        f"intermediation and market rails in the middle, and customer-facing deployment channels downstream. "
        f"Across {total} nodes, upstream coverage sits with {upstream}; midstream coverage with {midstream}; "
        f"and downstream coverage with {downstream}. Representative links include {relationships}. "
        "Use it to see where credit stress, fee pressure, or market-volume changes can travel next."
    )


def _build_learning_corner() -> str:
    return (
        "Learning Corner: In a financial stack, follow balance-sheet power first, fee extraction second, and end-user demand last. "
        "When rates, regulation, or volume slow down, the pressure usually appears first in funding and spread businesses, "
        "then in brokerage, asset-management, and payment rails."
    )


def _build_telegram_tldr(
    request: FinancePowerMapRequest,
    grouped: dict[str, tuple[FinancePowerMapNode, ...]],
    edges: tuple[FinancePowerMapEdge, ...],
) -> str:
    upstream = ", ".join(node.symbol for node in grouped["upstream"]) or "none"
    midstream = ", ".join(node.symbol for node in grouped["midstream"]) or "none"
    downstream = ", ".join(node.symbol for node in grouped["downstream"]) or "none"
    risk = edges[0].risk_note if edges and edges[0].risk_note else "Credit stress or fee compression can move across the stack."
    return "\n".join(
        [
            f"HK Finance Breadth-First Power Map: {request.market} Finance",
            f"Upstream: {upstream}",
            f"Midstream: {midstream}",
            f"Downstream: {downstream}",
            f"Main risk: {risk}",
            "Research only, not a trading instruction.",
        ]
    )


def _build_marketing_copy(
    request: FinancePowerMapRequest,
    grouped: dict[str, tuple[FinancePowerMapNode, ...]],
) -> str:
    total = sum(len(grouped[layer]) for layer in ("upstream", "midstream", "downstream"))
    return (
        f"Quant Researcher Desk turns {request.market} {request.sector.title()} into a compact breadth-first reference map "
        f"across {total} TradingView-finance nodes, showing where capital sourcing, intermediation, and end-market demand connect."
    )


def _relationship_map(report: FinancePowerMapReport) -> dict[str, object]:
    def items(nodes: tuple[FinancePowerMapNode, ...]) -> list[dict[str, str]]:
        return [
            {
                "symbol": node.symbol,
                "name": node.name,
                "industry": node.tradingview_industry,
            }
            for node in nodes
        ]

    return {
        "columns": [
            {"label": "Upstream", "items": items(report.upstream)},
            {"label": "Midstream", "items": items(report.midstream)},
            {"label": "Downstream", "items": items(report.downstream)},
        ],
        "edges": [
            {"source": edge.source_symbol, "target": edge.target_symbol, "relationship": edge.relationship}
            for edge in report.edges
        ],
    }


def _node_rows(report: FinancePowerMapReport) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for node in (*report.upstream, *report.midstream, *report.downstream):
        rows.append(
            {
                "layer": node.layer,
                "symbol": node.symbol,
                "name": node.name,
                "tradingview_sector": node.tradingview_sector,
                "tradingview_industry": node.tradingview_industry,
                "role": node.role,
                "catalyst": node.catalyst,
                "risk": node.risk,
            }
        )
    return rows


def _edge_rows(report: FinancePowerMapReport) -> list[dict[str, str]]:
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


def _fixture_key(market: str, sector: str) -> tuple[str, str]:
    return market.strip().upper(), sector.strip().lower()


_FIXTURE_NODES: dict[tuple[str, str], tuple[FinancePowerMapNode, ...]] = {
    _fixture_key("HK", "finance"): (
        FinancePowerMapNode(
            symbol="HK.LIST1079",
            name="Banks",
            market="HK",
            layer="upstream",
            tradingview_sector="Financials",
            tradingview_industry="Banks",
            role="Balance-sheet funding and deposit franchises",
            catalyst="Rate moves and deposit mix shift balance-sheet power quickly.",
            risk="Funding cost pressure can compress net interest margin.",
            why_it_matters="Banks supply the liquidity backbone that powers the rest of the finance stack.",
        ),
        FinancePowerMapNode(
            symbol="HK.LIST1003",
            name="Insurance",
            market="HK",
            layer="upstream",
            tradingview_sector="Financials",
            tradingview_industry="Insurance",
            role="Policy float and long-duration capital pools",
            catalyst="Premium growth and asset yields can widen investable float.",
            risk="Claims shocks or market drawdowns can hit capital adequacy.",
            why_it_matters="Insurance creates durable capital pools that feed allocation and deployment.",
        ),
        FinancePowerMapNode(
            symbol="HK.LIST1004",
            name="Credit Services",
            market="HK",
            layer="downstream",
            tradingview_sector="Financials",
            tradingview_industry="Credit Services",
            role="Consumer and SME credit demand",
            catalyst="Household credit demand and merchant financing shape volume.",
            risk="Delinquencies can rise quickly when the real economy softens.",
            why_it_matters="Credit services are where balance-sheet power reaches end borrowers.",
        ),
        FinancePowerMapNode(
            symbol="HK.LIST1068",
            name="Securities & Brokerage",
            market="HK",
            layer="midstream",
            tradingview_sector="Financials",
            tradingview_industry="Securities & Brokerage",
            role="Order flow, trade execution, and market access",
            catalyst="Trading volume and market volatility lift fee pools.",
            risk="Market activity can contract faster than research or distribution costs.",
            why_it_matters="Brokerage is the transmission belt between funding power and end-user investing.",
        ),
        FinancePowerMapNode(
            symbol="HK.LIST1030",
            name="Investment & Asset Management",
            market="HK",
            layer="midstream",
            tradingview_sector="Financials",
            tradingview_industry="Investment & Asset Management",
            role="Capital allocation and fee packaging",
            catalyst="AUM expansion and product mix improve recurring fee visibility.",
            risk="Risk-off flows and lower market values can trim fee base quickly.",
            why_it_matters="Asset managers convert balance-sheet capital into managed exposure.",
        ),
        FinancePowerMapNode(
            symbol="HK.LIST1007",
            name="Other Financial Services",
            market="HK",
            layer="midstream",
            tradingview_sector="Financials",
            tradingview_industry="Other Financial Services",
            role="Specialty finance, trust, custody, and structured rails",
            catalyst="Operational leverage rises when specialty finance and trust flows compound.",
            risk="Complex fee structures and balance-sheet opacity can hide early stress.",
            why_it_matters="This bucket often carries the plumbing that makes the rest of the stack usable.",
        ),
        FinancePowerMapNode(
            symbol="HK.LIST23362",
            name="Payment services",
            market="HK",
            layer="downstream",
            tradingview_sector="Financials",
            tradingview_industry="Payment services",
            role="Transaction rails and merchant acceptance",
            catalyst="Higher transaction volumes and merchant adoption lift payment economics.",
            risk="Fee compression or fraud losses can erode take rates.",
            why_it_matters="Payments are the customer-facing rail where finance becomes usable in daily life.",
        ),
        FinancePowerMapNode(
            symbol="HK.LIST1311",
            name="REITs",
            market="HK",
            layer="downstream",
            tradingview_sector="Financials",
            tradingview_industry="REITs",
            role="Property income deployment and yield packaging",
            catalyst="Yield demand and property stabilisation support capital deployment.",
            risk="Refinancing risk and occupancy swings can break the income story.",
            why_it_matters="REITs show how capital is ultimately deployed into real assets and cash flow.",
        ),
    ),
}


_FIXTURE_EDGES: dict[tuple[str, str], tuple[FinancePowerMapEdge, ...]] = {
    _fixture_key("HK", "finance"): (
        FinancePowerMapEdge(
            source_symbol="HK.LIST1079",
            target_symbol="HK.LIST1068",
            relationship="deposit funding supports brokerage and market access",
            evidence="Banks and brokers share capital-market liquidity and client flow.",
            risk_note="A funding squeeze can lower market activity and fee generation.",
        ),
        FinancePowerMapEdge(
            source_symbol="HK.LIST1079",
            target_symbol="HK.LIST1004",
            relationship="bank balance sheets support consumer and SME credit origination",
            evidence="Retail credit often depends on the cost of wholesale and deposit funding.",
            risk_note="Credit loss cycles can pressure spreads and provisioning.",
        ),
        FinancePowerMapEdge(
            source_symbol="HK.LIST1003",
            target_symbol="HK.LIST1030",
            relationship="policy float feeds long-duration asset allocation",
            evidence="Insurance capital is typically invested through managed portfolios and mandates.",
            risk_note="Market drawdowns can reduce investable float and fee base.",
        ),
        FinancePowerMapEdge(
            source_symbol="HK.LIST1003",
            target_symbol="HK.LIST1311",
            relationship="insurance capital can flow into real-asset yield structures",
            evidence="REIT allocations are common destinations for long-duration capital.",
            risk_note="Property valuation resets can hit the downstream yield story.",
        ),
        FinancePowerMapEdge(
            source_symbol="HK.LIST1068",
            target_symbol="HK.LIST23362",
            relationship="brokerage rails overlap with merchant and consumer payments",
            evidence="Order flow, custody, and wallet usage often travel through the same digital rails.",
            risk_note="Lower transaction intensity can reduce cross-sell and interchange value.",
        ),
        FinancePowerMapEdge(
            source_symbol="HK.LIST1030",
            target_symbol="HK.LIST1311",
            relationship="managed capital is deployed into income-producing property",
            evidence="Asset managers often route capital into listed real-estate income vehicles.",
            risk_note="Rate repricing can lower REIT valuations and inflows.",
        ),
        FinancePowerMapEdge(
            source_symbol="HK.LIST1007",
            target_symbol="HK.LIST23362",
            relationship="specialty finance products support payment and wallet usage",
            evidence="Custody, trust, and specialty-finance rails can sit behind transaction products.",
            risk_note="Complex products can hide early credit deterioration.",
        ),
        FinancePowerMapEdge(
            source_symbol="HK.LIST1004",
            target_symbol="HK.LIST23362",
            relationship="consumer credit demand is adjacent to payment and wallet behaviour",
            evidence="Borrowing demand and payment usage often rise and fall together in household finance.",
            risk_note="Delinquencies can expand when consumer demand weakens.",
        ),
    ),
}
