"""Sector value-chain trees for educational research reports."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Protocol

from quant_researcher_desk.industry_universe import (
    IndustryNode,
    SupplyChainEdge as IndustrySupplyChainEdge,
    load_industry_nodes_csv,
    load_supply_chain_edges_csv,
)


VALUE_CHAIN_ROLES = ("upstream", "midstream", "downstream")


class SectorTreeError(ValueError):
    """Raised when a sector tree report cannot be built."""


class SectorTreeProvider(Protocol):
    def get_company_profiles(self, market: str, sector: str) -> list["CompanyProfile"]:
        ...

    def get_value_chain_edges(self, market: str, sector: str) -> list["ValueChainEdge"]:
        ...


@dataclass(frozen=True)
class CompanyProfile:
    symbol: str
    name: str
    market: str
    sector: str
    industry: str
    value_chain_role: str
    business_summary: str
    key_risks: tuple[str, ...] = ()
    gics_sector: str = ""
    gics_industry_group: str = ""
    gics_industry: str = ""


@dataclass(frozen=True)
class ValueChainEdge:
    source_symbol: str
    target_symbol: str
    relationship: str
    evidence: str
    risk_note: str = ""


@dataclass(frozen=True)
class SectorTreeRequest:
    market: str
    sector: str
    focus_symbols: tuple[str, ...] = ()
    max_companies_per_group: int | None = None


@dataclass(frozen=True)
class SectorTreeReport:
    request: SectorTreeRequest
    upstream: tuple[CompanyProfile, ...]
    midstream: tuple[CompanyProfile, ...]
    downstream: tuple[CompanyProfile, ...]
    edges: tuple[ValueChainEdge, ...]
    risks: tuple[str, ...]
    educational_summary: str
    telegram_tldr: str
    marketing_copy: str
    analysis_level: str = "sector"
    gics_sector: str = ""
    gics_industry_group: str = ""
    drill_down_industries: tuple[str, ...] = ()


class FixtureSectorTreeProvider:
    """Deterministic local fixture provider for offline analysis and tests."""

    def __init__(
        self,
        profiles: dict[tuple[str, str], tuple[CompanyProfile, ...]] | None = None,
        edges: dict[tuple[str, str], tuple[ValueChainEdge, ...]] | None = None,
    ) -> None:
        self._profiles = profiles or _FIXTURE_PROFILES
        self._edges = edges or _FIXTURE_EDGES

    def get_company_profiles(self, market: str, sector: str) -> list[CompanyProfile]:
        return list(self._profiles.get(_fixture_key(market, sector), ()))

    def get_value_chain_edges(self, market: str, sector: str) -> list[ValueChainEdge]:
        return list(self._edges.get(_fixture_key(market, sector), ()))


class IndustryUniverseSectorTreeProvider:
    """Build GICS industry-group reports from the exported Moomoo universe."""

    def __init__(self, nodes_path: str | Path, edges_path: str | Path) -> None:
        self._nodes = load_industry_nodes_csv(nodes_path)
        self._edges = load_supply_chain_edges_csv(edges_path)

    def get_company_profiles(self, market: str, sector: str) -> list[CompanyProfile]:
        return [_node_to_profile(node, sector) for node in self._select_nodes(market, sector)]

    def get_value_chain_edges(self, market: str, sector: str) -> list[ValueChainEdge]:
        selected = self._select_nodes(market, sector)
        selected_ids = {node.node_id for node in selected}
        selected_codes = {node.node_id: node.code for node in selected}
        return [
            _industry_edge_to_value_chain_edge(edge, selected_codes)
            for edge in self._edges
            if edge.source_id in selected_ids and edge.target_id in selected_ids
        ]

    def _select_nodes(self, market: str, sector: str) -> tuple[IndustryNode, ...]:
        market = market.strip().upper()
        sector_key = " ".join(sector.strip().lower().split())
        exact = [
            node
            for node in self._nodes
            if node.market == market
            and node.plate_type == "INDUSTRY"
            and (
                _normalize_label(node.name) == sector_key
                or node.code.lower() == sector_key
                or _normalize_label(node.gics_industry_group) == sector_key
                or _normalize_label(node.gics_industry) == sector_key
            )
        ]
        if not exact:
            return ()
        target = exact[0]
        scope_nodes = [
            node
            for node in self._nodes
            if node.market == market
            and node.gics_industry_group == target.gics_industry_group
            and node.plate_type == "INDUSTRY"
            and node.value_chain_role in {*VALUE_CHAIN_ROLES, "enabler", "cross_chain"}
        ]
        selected: list[IndustryNode] = []
        for role in VALUE_CHAIN_ROLES:
            role_nodes = sorted(
                (node for node in scope_nodes if node.value_chain_role == role),
                key=lambda node: (node.gics_industry, node.research_priority, node.name),
            )
            if target.value_chain_role == role and target not in role_nodes:
                role_nodes.insert(0, target)
            selected.extend(role_nodes[:4])
        if not selected:
            selected.extend(sorted(scope_nodes, key=lambda node: (node.gics_industry, node.research_priority, node.name))[:8])
        if target not in selected:
            selected.append(target)
        return tuple(dict.fromkeys(selected))


def build_sector_tree_report(
    request: SectorTreeRequest,
    provider: SectorTreeProvider | None = None,
) -> SectorTreeReport:
    provider = provider or FixtureSectorTreeProvider()
    normalized_request = _normalize_request(request)
    profiles = provider.get_company_profiles(normalized_request.market, normalized_request.sector)
    edges = provider.get_value_chain_edges(normalized_request.market, normalized_request.sector)

    selected_profiles = _select_profiles(profiles, normalized_request)
    if not selected_profiles:
        raise SectorTreeError(
            f"No fixture data found for {normalized_request.market} {normalized_request.sector}."
        )

    grouped = _group_profiles(selected_profiles, normalized_request.max_companies_per_group)
    visible_profiles = tuple(profile for role in VALUE_CHAIN_ROLES for profile in grouped[role])
    selected_symbols = {profile.symbol for profile in visible_profiles}
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
    risks = _build_risks(visible_profiles, selected_edges)
    gics_sector, gics_industry_group, drill_down_industries = _summarize_gics(visible_profiles)
    analysis_level = "GICS industry group" if gics_industry_group else "sector"
    educational_summary = _build_educational_summary(normalized_request, grouped, selected_edges, analysis_level, gics_sector, gics_industry_group, drill_down_industries)
    telegram_tldr = _build_telegram_tldr(normalized_request, grouped, risks, analysis_level, gics_industry_group)
    marketing_copy = _build_marketing_copy(normalized_request, grouped, analysis_level, gics_industry_group)

    return SectorTreeReport(
        request=normalized_request,
        upstream=grouped["upstream"],
        midstream=grouped["midstream"],
        downstream=grouped["downstream"],
        edges=selected_edges,
        risks=risks,
        educational_summary=educational_summary,
        telegram_tldr=telegram_tldr,
        marketing_copy=marketing_copy,
        analysis_level=analysis_level,
        gics_sector=gics_sector,
        gics_industry_group=gics_industry_group,
        drill_down_industries=drill_down_industries,
    )


def _node_to_profile(node: IndustryNode, requested_sector: str) -> CompanyProfile:
    value_chain_role = node.value_chain_role if node.value_chain_role in VALUE_CHAIN_ROLES else "midstream"
    return CompanyProfile(
        symbol=node.code,
        name=node.name,
        market=node.market,
        sector=node.gics_sector,
        industry=node.gics_industry,
        value_chain_role=value_chain_role,
        business_summary=(
            f"{node.name} is a Moomoo {node.plate_type.lower()} plate used as a drill-down industry under "
            f"the {node.gics_industry_group} GICS industry group; locally it sits in the "
            f"{node.value_chain_role} research layer."
        ),
        key_risks=(
            "GICS overlay and plate-level role are research starting points; validate constituents and company filings before using them as evidence.",
        ),
        gics_sector=node.gics_sector,
        gics_industry_group=node.gics_industry_group,
        gics_industry=node.gics_industry,
    )


def _industry_edge_to_value_chain_edge(
    edge: IndustrySupplyChainEdge,
    selected_codes: dict[str, str],
) -> ValueChainEdge:
    return ValueChainEdge(
        source_symbol=selected_codes[edge.source_id],
        target_symbol=selected_codes[edge.target_id],
        relationship=edge.relationship,
        evidence=edge.rationale,
        risk_note="This edge is heuristic until replaced with sourced company-level evidence.",
    )


def _normalize_request(request: SectorTreeRequest) -> SectorTreeRequest:
    market = request.market.strip().upper()
    sector = _normalize_label(request.sector)
    focus_symbols = tuple(sorted({symbol.strip().upper() for symbol in request.focus_symbols if symbol.strip()}))
    if not market:
        raise SectorTreeError("Market is required.")
    if not sector:
        raise SectorTreeError("Sector is required.")
    if request.max_companies_per_group is not None and request.max_companies_per_group < 1:
        raise SectorTreeError("max_companies_per_group must be positive when provided.")
    return SectorTreeRequest(
        market=market,
        sector=sector,
        focus_symbols=focus_symbols,
        max_companies_per_group=request.max_companies_per_group,
    )


def _select_profiles(
    profiles: Iterable[CompanyProfile],
    request: SectorTreeRequest,
) -> tuple[CompanyProfile, ...]:
    normalized = [_normalize_profile(profile) for profile in profiles]
    if request.focus_symbols:
        focus = set(request.focus_symbols)
        normalized = [profile for profile in normalized if profile.symbol in focus]
    return tuple(
        sorted(
            normalized,
            key=lambda profile: (
                VALUE_CHAIN_ROLES.index(profile.value_chain_role),
                profile.symbol,
            ),
        )
    )


def _normalize_profile(profile: CompanyProfile) -> CompanyProfile:
    role = profile.value_chain_role.strip().lower()
    if role not in VALUE_CHAIN_ROLES:
        raise SectorTreeError(f"Unsupported value-chain role for {profile.symbol}: {profile.value_chain_role}")
    return CompanyProfile(
        symbol=profile.symbol.strip().upper(),
        name=profile.name.strip(),
        market=profile.market.strip().upper(),
        sector=" ".join(profile.sector.strip().lower().split()),
        industry=profile.industry.strip(),
        value_chain_role=role,
        business_summary=profile.business_summary.strip(),
        key_risks=tuple(risk.strip() for risk in profile.key_risks if risk.strip()),
        gics_sector=profile.gics_sector.strip(),
        gics_industry_group=profile.gics_industry_group.strip(),
        gics_industry=profile.gics_industry.strip(),
    )


def _group_profiles(
    profiles: tuple[CompanyProfile, ...],
    max_companies_per_group: int | None,
) -> dict[str, tuple[CompanyProfile, ...]]:
    grouped: dict[str, tuple[CompanyProfile, ...]] = {}
    for role in VALUE_CHAIN_ROLES:
        role_profiles = tuple(profile for profile in profiles if profile.value_chain_role == role)
        grouped[role] = role_profiles[:max_companies_per_group] if max_companies_per_group else role_profiles
    return grouped


def _build_risks(
    profiles: tuple[CompanyProfile, ...],
    edges: tuple[ValueChainEdge, ...],
) -> tuple[str, ...]:
    risks: list[str] = []
    for profile in profiles:
        for risk in profile.key_risks:
            risks.append(f"{profile.symbol}: {risk}")
    for edge in edges:
        if edge.risk_note:
            risks.append(f"{edge.source_symbol}->{edge.target_symbol}: {edge.risk_note}")
    if not risks:
        risks.append("Research output only; validate sector exposure and company filings before use.")
    return tuple(dict.fromkeys(risks))


def _build_educational_summary(
    request: SectorTreeRequest,
    grouped: dict[str, tuple[CompanyProfile, ...]],
    edges: tuple[ValueChainEdge, ...],
    analysis_level: str,
    gics_sector: str,
    gics_industry_group: str,
    drill_down_industries: tuple[str, ...],
) -> str:
    total = sum(len(grouped[role]) for role in VALUE_CHAIN_ROLES)
    scope = gics_industry_group or request.sector.title()
    drill_down = ", ".join(drill_down_industries) if drill_down_industries else "available company and industry rows"
    sections = [
        f"The {request.market} {scope} map is best read as a {analysis_level} value-chain briefing, not a ticker list.",
        f"GICS sector context: {gics_sector or 'local fixture coverage'}; drill-down industries: {drill_down}.",
        f"Across {total} coverage nodes, the structure separates supply constraints, platform economics, and end-market demand.",
        f"Upstream exposure sits with {_format_symbols(grouped['upstream'])}.",
        f"Midstream platforms include {_format_symbols(grouped['midstream'])}.",
        f"Downstream demand is represented by {_format_symbols(grouped['downstream'])}.",
    ]
    if edges:
        relationships = "; ".join(
            f"{edge.source_symbol} to {edge.target_symbol} ({edge.relationship})" for edge in edges
        )
        sections.append(f"Representative links: {relationships}.")
    sections.append("The useful takeaway is where pressure can travel: capex cycles can hit suppliers first, while regulation, subsidy, and consumer demand tend to show up in platform and downstream margins.")
    sections.append("Use this as a learning map, not as a valuation, forecast, or trading signal.")
    return " ".join(sections)


def _build_telegram_tldr(
    request: SectorTreeRequest,
    grouped: dict[str, tuple[CompanyProfile, ...]],
    risks: tuple[str, ...],
    analysis_level: str,
    gics_industry_group: str,
) -> str:
    scope = gics_industry_group or request.sector.title()
    return "\n".join(
        [
            f"Sector Tree TLDR: {request.market} {scope}",
            f"Analysis level: {analysis_level}",
            f"Upstream: {_format_symbols(grouped['upstream'])}",
            f"Midstream: {_format_symbols(grouped['midstream'])}",
            f"Downstream: {_format_symbols(grouped['downstream'])}",
            f"Main risk: {risks[0]}",
            "Educational research only, not a trading instruction.",
        ]
    )


def _build_marketing_copy(
    request: SectorTreeRequest,
    grouped: dict[str, tuple[CompanyProfile, ...]],
    analysis_level: str,
    gics_industry_group: str,
) -> str:
    total = sum(len(grouped[role]) for role in VALUE_CHAIN_ROLES)
    scope = gics_industry_group or request.sector.title()
    return (
        f"Quant Researcher Desk turns {request.market} {scope} coverage into a compact "
        f"{analysis_level} field note across {total} coverage nodes. The goal is to help readers see who supplies the stack, "
        "who controls the platform layer, and where demand or regulation can change the earnings path."
    )


def _format_symbols(profiles: tuple[CompanyProfile, ...]) -> str:
    if not profiles:
        return "none in scope"
    return ", ".join(f"{profile.symbol} ({profile.name})" for profile in profiles)


def _fixture_key(market: str, sector: str) -> tuple[str, str]:
    return market.strip().upper(), _normalize_label(sector)


def _normalize_label(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _summarize_gics(profiles: tuple[CompanyProfile, ...]) -> tuple[str, str, tuple[str, ...]]:
    sectors = tuple(dict.fromkeys(profile.gics_sector for profile in profiles if profile.gics_sector))
    groups = tuple(dict.fromkeys(profile.gics_industry_group for profile in profiles if profile.gics_industry_group))
    industries = tuple(sorted({profile.gics_industry for profile in profiles if profile.gics_industry}))
    return (
        sectors[0] if len(sectors) == 1 else "",
        groups[0] if len(groups) == 1 else "",
        industries,
    )


_FIXTURE_PROFILES: dict[tuple[str, str], tuple[CompanyProfile, ...]] = {
    _fixture_key("US", "semiconductors"): (
        CompanyProfile(
            symbol="ASML",
            name="ASML Holding",
            market="US",
            sector="semiconductors",
            industry="Semiconductor equipment",
            value_chain_role="upstream",
            business_summary="Lithography equipment supplier used by advanced chip manufacturers.",
            key_risks=("Export controls can restrict tool shipments.",),
        ),
        CompanyProfile(
            symbol="AMAT",
            name="Applied Materials",
            market="US",
            sector="semiconductors",
            industry="Wafer fabrication equipment",
            value_chain_role="upstream",
            business_summary="Process equipment provider for deposition, etch, and inspection workflows.",
            key_risks=("Capital-equipment demand can fall quickly in semiconductor downcycles.",),
        ),
        CompanyProfile(
            symbol="TSM",
            name="Taiwan Semiconductor Manufacturing",
            market="US",
            sector="semiconductors",
            industry="Foundry",
            value_chain_role="midstream",
            business_summary="Contract manufacturer that converts chip designs into finished wafers.",
            key_risks=("Customer concentration and geopolitical exposure can affect capacity planning.",),
        ),
        CompanyProfile(
            symbol="NVDA",
            name="NVIDIA",
            market="US",
            sector="semiconductors",
            industry="Accelerated computing",
            value_chain_role="downstream",
            business_summary="Chip designer and platform supplier exposed to AI infrastructure demand.",
            key_risks=("Demand expectations can reprice sharply when accelerator supply or spending plans change.",),
        ),
        CompanyProfile(
            symbol="AAPL",
            name="Apple",
            market="US",
            sector="semiconductors",
            industry="Consumer devices",
            value_chain_role="downstream",
            business_summary="End-market device company using advanced semiconductors in consumer hardware.",
            key_risks=("Consumer device cycles can alter downstream chip demand.",),
        ),
    ),
    _fixture_key("HK", "internet platforms"): (
        CompanyProfile(
            symbol="HK.0981",
            name="SMIC",
            market="HK",
            sector="internet platforms",
            industry="Foundry infrastructure",
            value_chain_role="upstream",
            business_summary="Domestic manufacturing capacity that can support platform hardware ecosystems.",
            key_risks=("Technology access constraints can affect node progression.",),
        ),
        CompanyProfile(
            symbol="HK.0700",
            name="Tencent",
            market="HK",
            sector="internet platforms",
            industry="Social and gaming platforms",
            value_chain_role="midstream",
            business_summary="Operates digital platforms connecting users, content, payments, and cloud services.",
            key_risks=("Regulatory policy changes can affect content, gaming, and fintech economics.",),
        ),
        CompanyProfile(
            symbol="HK.9988",
            name="Alibaba",
            market="HK",
            sector="internet platforms",
            industry="E-commerce and cloud",
            value_chain_role="midstream",
            business_summary="Runs commerce, logistics coordination, and cloud services across merchants and consumers.",
            key_risks=("Competitive pricing pressure can compress platform margins.",),
        ),
        CompanyProfile(
            symbol="HK.3690",
            name="Meituan",
            market="HK",
            sector="internet platforms",
            industry="Local services",
            value_chain_role="downstream",
            business_summary="Consumer-facing local services platform for delivery, travel, and in-store demand.",
            key_risks=("Delivery economics depend on subsidies, labor costs, and merchant take rates.",),
        ),
    ),
    _fixture_key("HK", "tech"): (
        CompanyProfile(
            symbol="HK.0522",
            name="ASMPT",
            market="HK",
            sector="tech",
            industry="Semiconductor equipment",
            value_chain_role="upstream",
            business_summary="Supplies assembly and packaging equipment used in semiconductor back-end production.",
            key_risks=("Semiconductor capex cycles can create sharp order volatility.",),
        ),
        CompanyProfile(
            symbol="HK.0981",
            name="SMIC",
            market="HK",
            sector="tech",
            industry="Foundry infrastructure",
            value_chain_role="upstream",
            business_summary="Domestic manufacturing capacity that supports China technology hardware ecosystems.",
            key_risks=("Technology access constraints can affect node progression.",),
        ),
        CompanyProfile(
            symbol="HK.0700",
            name="Tencent",
            market="HK",
            sector="tech",
            industry="Social, gaming, cloud, and payments",
            value_chain_role="midstream",
            business_summary="Operates digital platforms connecting users, content, payments, cloud, and enterprise services.",
            key_risks=("Regulatory policy changes can affect content, gaming, and fintech economics.",),
        ),
        CompanyProfile(
            symbol="HK.9988",
            name="Alibaba",
            market="HK",
            sector="tech",
            industry="E-commerce, cloud, and logistics coordination",
            value_chain_role="midstream",
            business_summary="Runs commerce and cloud platforms that connect merchants, consumers, and enterprise workloads.",
            key_risks=("Competitive pricing pressure can compress platform and cloud margins.",),
        ),
        CompanyProfile(
            symbol="HK.1810",
            name="Xiaomi",
            market="HK",
            sector="tech",
            industry="Consumer electronics and smart devices",
            value_chain_role="downstream",
            business_summary="Packages chips, operating systems, internet services, and distribution into consumer hardware demand.",
            key_risks=("Hardware margins remain sensitive to component costs and product-cycle timing.",),
        ),
        CompanyProfile(
            symbol="HK.3690",
            name="Meituan",
            market="HK",
            sector="tech",
            industry="Local services",
            value_chain_role="downstream",
            business_summary="Consumer-facing local services platform for delivery, travel, and in-store demand.",
            key_risks=("Delivery economics depend on subsidies, labor costs, and merchant take rates.",),
        ),
    ),
    _fixture_key("US", "energy"): (
        CompanyProfile(
            symbol="SLB",
            name="SLB",
            market="US",
            sector="energy",
            industry="Oilfield services",
            value_chain_role="upstream",
            business_summary="Provides drilling, reservoir, and digital services used by global exploration and production companies.",
            key_risks=("Service demand can fall quickly when producers cut capex.",),
        ),
        CompanyProfile(
            symbol="HAL",
            name="Halliburton",
            market="US",
            sector="energy",
            industry="Oilfield services",
            value_chain_role="upstream",
            business_summary="Supplies completion and production services tied to North American activity levels.",
            key_risks=("North America rig activity is cyclical and sensitive to commodity prices.",),
        ),
        CompanyProfile(
            symbol="XOM",
            name="Exxon Mobil",
            market="US",
            sector="energy",
            industry="Integrated oil and gas",
            value_chain_role="midstream",
            business_summary="Combines upstream production, refining, chemicals, and capital returns.",
            key_risks=("Oil and gas price volatility can dominate operating leverage.",),
        ),
        CompanyProfile(
            symbol="CVX",
            name="Chevron",
            market="US",
            sector="energy",
            industry="Integrated oil and gas",
            value_chain_role="midstream",
            business_summary="Integrated producer with upstream, LNG, refining, and shareholder-return exposure.",
            key_risks=("Project execution and commodity prices can shift free cash flow expectations.",),
        ),
        CompanyProfile(
            symbol="VLO",
            name="Valero Energy",
            market="US",
            sector="energy",
            industry="Refining",
            value_chain_role="downstream",
            business_summary="Refiner exposed to crack spreads, product demand, and feedstock differentials.",
            key_risks=("Refining margins can compress when product demand softens or supply normalizes.",),
        ),
        CompanyProfile(
            symbol="PSX",
            name="Phillips 66",
            market="US",
            sector="energy",
            industry="Refining and midstream",
            value_chain_role="downstream",
            business_summary="Operates refining, chemicals, marketing, and midstream assets tied to end-market fuel demand.",
            key_risks=("Fuel demand weakness can reduce downstream margin leverage.",),
        ),
    ),
    _fixture_key("US", "banks"): (
        CompanyProfile(
            symbol="JPM",
            name="JPMorgan Chase",
            market="US",
            sector="banks",
            industry="Universal banking",
            value_chain_role="upstream",
            business_summary="Large deposit base and balance sheet provide funding, credit, and market liquidity.",
            key_risks=("Credit deterioration and deposit repricing can pressure returns.",),
        ),
        CompanyProfile(
            symbol="BAC",
            name="Bank of America",
            market="US",
            sector="banks",
            industry="Consumer and commercial banking",
            value_chain_role="upstream",
            business_summary="Deposit-heavy bank exposed to net interest income and consumer credit quality.",
            key_risks=("Lower rates or higher funding costs can pressure net interest income.",),
        ),
        CompanyProfile(
            symbol="GS",
            name="Goldman Sachs",
            market="US",
            sector="banks",
            industry="Investment banking and markets",
            value_chain_role="midstream",
            business_summary="Capital markets intermediary exposed to advisory, underwriting, trading, and asset management.",
            key_risks=("Deal activity and trading revenue can be uneven across cycles.",),
        ),
        CompanyProfile(
            symbol="MS",
            name="Morgan Stanley",
            market="US",
            sector="banks",
            industry="Wealth management and markets",
            value_chain_role="midstream",
            business_summary="Connects institutional markets activity with a large wealth-management platform.",
            key_risks=("Market drawdowns can reduce client assets and transaction activity.",),
        ),
        CompanyProfile(
            symbol="V",
            name="Visa",
            market="US",
            sector="banks",
            industry="Payments network",
            value_chain_role="downstream",
            business_summary="Consumer and business spending flow through its global payments network.",
            key_risks=("Regulation and slower spending growth can affect volume and fee economics.",),
        ),
        CompanyProfile(
            symbol="MA",
            name="Mastercard",
            market="US",
            sector="banks",
            industry="Payments network",
            value_chain_role="downstream",
            business_summary="Payment network exposed to cross-border travel, consumer spend, and digital acceptance.",
            key_risks=("Cross-border weakness and fee regulation can pressure growth.",),
        ),
    ),
    _fixture_key("HK", "consumer"): (
        CompanyProfile(
            symbol="HK.1928",
            name="Sands China",
            market="HK",
            sector="consumer",
            industry="Gaming and leisure",
            value_chain_role="upstream",
            business_summary="Macau operator exposed to travel flows, premium mass demand, and discretionary spending.",
            key_risks=("Tourism and policy changes can alter gaming revenue quickly.",),
        ),
        CompanyProfile(
            symbol="HK.0019",
            name="Swire Pacific",
            market="HK",
            sector="consumer",
            industry="Conglomerate and beverages",
            value_chain_role="upstream",
            business_summary="Holds consumer, aviation, property, and beverage distribution exposure.",
            key_risks=("Mixed asset exposure can dilute a clean consumer read-through.",),
        ),
        CompanyProfile(
            symbol="HK.9988",
            name="Alibaba",
            market="HK",
            sector="consumer",
            industry="E-commerce platform",
            value_chain_role="midstream",
            business_summary="Commerce platform that aggregates merchant demand, logistics coordination, and consumer traffic.",
            key_risks=("Price competition can compress marketplace monetization.",),
        ),
        CompanyProfile(
            symbol="HK.3690",
            name="Meituan",
            market="HK",
            sector="consumer",
            industry="Local services",
            value_chain_role="midstream",
            business_summary="Connects merchants, delivery networks, restaurants, hotels, and consumers.",
            key_risks=("Subsidy competition can reduce operating leverage.",),
        ),
        CompanyProfile(
            symbol="HK.2331",
            name="Li Ning",
            market="HK",
            sector="consumer",
            industry="Sportswear",
            value_chain_role="downstream",
            business_summary="Consumer brand exposed to apparel demand, inventory discipline, and channel execution.",
            key_risks=("Inventory build and discounting can pressure margins.",),
        ),
        CompanyProfile(
            symbol="HK.2020",
            name="ANTA Sports",
            market="HK",
            sector="consumer",
            industry="Sportswear",
            value_chain_role="downstream",
            business_summary="Sportswear platform exposed to domestic consumption and brand portfolio execution.",
            key_risks=("Consumer softness can show up in sell-through and distributor inventory.",),
        ),
    ),
    _fixture_key("US", "defense"): (
        CompanyProfile(
            symbol="LHX",
            name="L3Harris Technologies",
            market="US",
            sector="defense",
            industry="Mission systems",
            value_chain_role="upstream",
            business_summary="Supplies communications, sensors, and mission systems across defense programs.",
            key_risks=("Program delays and integration risk can affect margins.",),
        ),
        CompanyProfile(
            symbol="HWM",
            name="Howmet Aerospace",
            market="US",
            sector="defense",
            industry="Aerospace components",
            value_chain_role="upstream",
            business_summary="Provides engineered components used across aerospace and defense platforms.",
            key_risks=("Supply-chain constraints can limit production ramp timing.",),
        ),
        CompanyProfile(
            symbol="LMT",
            name="Lockheed Martin",
            market="US",
            sector="defense",
            industry="Defense prime",
            value_chain_role="midstream",
            business_summary="Prime contractor across aircraft, missiles, space, and integrated defense systems.",
            key_risks=("Budget timing and fixed-price contracts can pressure execution.",),
        ),
        CompanyProfile(
            symbol="RTX",
            name="RTX",
            market="US",
            sector="defense",
            industry="Aerospace and defense systems",
            value_chain_role="midstream",
            business_summary="Combines defense systems with commercial aerospace engine and aftermarket exposure.",
            key_risks=("Engine inspection and production issues can affect cash flow.",),
        ),
        CompanyProfile(
            symbol="NOC",
            name="Northrop Grumman",
            market="US",
            sector="defense",
            industry="Defense prime",
            value_chain_role="downstream",
            business_summary="Prime contractor with space, strategic deterrence, and defense electronics exposure.",
            key_risks=("Large long-cycle programs carry schedule and cost risk.",),
        ),
        CompanyProfile(
            symbol="GD",
            name="General Dynamics",
            market="US",
            sector="defense",
            industry="Defense and aerospace",
            value_chain_role="downstream",
            business_summary="Exposed to combat systems, marine systems, IT services, and business jets.",
            key_risks=("Marine backlog execution and Gulfstream cycles can move earnings expectations.",),
        ),
    ),
}


_FIXTURE_EDGES: dict[tuple[str, str], tuple[ValueChainEdge, ...]] = {
    _fixture_key("US", "semiconductors"): (
        ValueChainEdge(
            source_symbol="ASML",
            target_symbol="TSM",
            relationship="lithography equipment enables advanced-node manufacturing",
            evidence="Equipment suppliers support foundry capacity and process migration.",
            risk_note="Tool availability can become a bottleneck for advanced capacity.",
        ),
        ValueChainEdge(
            source_symbol="AMAT",
            target_symbol="TSM",
            relationship="wafer-fabrication equipment supports foundry process steps",
            evidence="Deposition and inspection tools are required across foundry lines.",
            risk_note="Equipment order cuts can indicate foundry capex cyclicality.",
        ),
        ValueChainEdge(
            source_symbol="TSM",
            target_symbol="NVDA",
            relationship="foundry capacity supports accelerator production",
            evidence="Fabless designers rely on foundry partners for chip manufacturing.",
            risk_note="Capacity allocation can influence shipment timing.",
        ),
        ValueChainEdge(
            source_symbol="TSM",
            target_symbol="AAPL",
            relationship="advanced wafers support consumer-device silicon",
            evidence="Consumer hardware companies depend on leading-edge chip supply.",
            risk_note="Device demand swings can feed back into foundry utilization.",
        ),
    ),
    _fixture_key("HK", "internet platforms"): (
        ValueChainEdge(
            source_symbol="HK.0981",
            target_symbol="HK.0700",
            relationship="domestic compute supply can support cloud and AI services",
            evidence="Platform operators depend on data-center and compute supply chains.",
            risk_note="Hardware constraints can limit service scaling.",
        ),
        ValueChainEdge(
            source_symbol="HK.0700",
            target_symbol="HK.3690",
            relationship="payments and traffic channels can support local-service demand",
            evidence="Consumer platforms often share payment, identity, and advertising rails.",
            risk_note="Policy or fee changes can alter ecosystem economics.",
        ),
        ValueChainEdge(
            source_symbol="HK.9988",
            target_symbol="HK.3690",
            relationship="merchant digitization overlaps with local-service fulfillment",
            evidence="Commerce platforms and local-service platforms compete for merchant budgets.",
            risk_note="Competition can raise acquisition and subsidy costs.",
        ),
    ),
    _fixture_key("HK", "tech"): (
        ValueChainEdge(
            source_symbol="HK.0522",
            target_symbol="HK.0981",
            relationship="assembly and packaging tooling supports semiconductor manufacturing capacity",
            evidence="Back-end equipment is part of the production stack behind technology hardware supply.",
            risk_note="Equipment-cycle weakness can signal pressure on downstream hardware demand.",
        ),
        ValueChainEdge(
            source_symbol="HK.0981",
            target_symbol="HK.1810",
            relationship="domestic semiconductor supply can support smart-device ecosystems",
            evidence="Consumer hardware companies depend on chip availability and component cost discipline.",
            risk_note="Foundry limitations can constrain hardware feature cadence or margin recovery.",
        ),
        ValueChainEdge(
            source_symbol="HK.0700",
            target_symbol="HK.3690",
            relationship="payments, identity, and traffic channels support local-service demand",
            evidence="Platform companies often share digital payment, advertising, and user-acquisition rails.",
            risk_note="Policy or fee changes can alter ecosystem economics.",
        ),
        ValueChainEdge(
            source_symbol="HK.9988",
            target_symbol="HK.3690",
            relationship="merchant digitization overlaps with local-service fulfillment",
            evidence="Commerce and local-service platforms compete for merchant budgets and consumer frequency.",
            risk_note="Competition can raise acquisition and subsidy costs.",
        ),
        ValueChainEdge(
            source_symbol="HK.9988",
            target_symbol="HK.1810",
            relationship="cloud and commerce rails support connected-device distribution",
            evidence="Hardware ecosystems can draw on cloud services, marketplaces, and logistics channels.",
            risk_note="Weak consumer electronics demand can reduce channel leverage.",
        ),
    ),
    _fixture_key("US", "energy"): (
        ValueChainEdge(
            source_symbol="SLB",
            target_symbol="XOM",
            relationship="oilfield services support upstream production activity",
            evidence="Integrated producers depend on service providers for drilling, completion, and reservoir workflows.",
            risk_note="Lower producer capex can hit service revenue before downstream demand changes.",
        ),
        ValueChainEdge(
            source_symbol="HAL",
            target_symbol="CVX",
            relationship="completion activity supports production growth and maintenance",
            evidence="Service intensity rises when producers increase field activity.",
            risk_note="Activity cuts can signal a more defensive capital plan.",
        ),
        ValueChainEdge(
            source_symbol="XOM",
            target_symbol="VLO",
            relationship="crude and product markets shape refining economics",
            evidence="Integrated producers and refiners are connected through feedstock costs and product demand.",
            risk_note="Weak product demand can compress crack spreads even when crude supply is tight.",
        ),
        ValueChainEdge(
            source_symbol="CVX",
            target_symbol="PSX",
            relationship="upstream supply and downstream fuel demand transmit margin pressure",
            evidence="Refiners and integrated producers both respond to commodity, transport, and end-demand signals.",
            risk_note="Commodity volatility can blur operating performance.",
        ),
    ),
    _fixture_key("US", "banks"): (
        ValueChainEdge(
            source_symbol="JPM",
            target_symbol="GS",
            relationship="large-bank balance sheets support capital markets liquidity",
            evidence="Funding, underwriting, and trading ecosystems are linked through client risk appetite.",
            risk_note="Risk-off markets can reduce issuance and trading activity.",
        ),
        ValueChainEdge(
            source_symbol="BAC",
            target_symbol="MS",
            relationship="deposit and wealth channels transmit rate-cycle pressure",
            evidence="Consumer deposits, client assets, and market levels influence banking and wealth revenue.",
            risk_note="Deposit betas and asset-price declines can pressure fees and spreads together.",
        ),
        ValueChainEdge(
            source_symbol="JPM",
            target_symbol="V",
            relationship="card issuance and payment networks connect banks to consumer spending",
            evidence="Bank-issued cards generate transaction volume over network rails.",
            risk_note="Consumer slowdown can affect both credit quality and payment volume.",
        ),
        ValueChainEdge(
            source_symbol="BAC",
            target_symbol="MA",
            relationship="consumer accounts and payment rails share spend-cycle exposure",
            evidence="Payments networks reflect nominal spending, travel, and digital acceptance.",
            risk_note="Regulatory pressure on fees can change downstream economics.",
        ),
    ),
    _fixture_key("HK", "consumer"): (
        ValueChainEdge(
            source_symbol="HK.1928",
            target_symbol="HK.2331",
            relationship="travel and discretionary spending provide a read-through for consumer appetite",
            evidence="Leisure demand and retail demand both reflect household confidence and tourism flows.",
            risk_note="Tourism recovery can diverge from domestic retail spending.",
        ),
        ValueChainEdge(
            source_symbol="HK.0019",
            target_symbol="HK.2020",
            relationship="distribution and brand exposure connect channel health to consumer brands",
            evidence="Conglomerate consumer assets can indicate distribution and demand conditions.",
            risk_note="Channel inventory can hide real end-demand weakness.",
        ),
        ValueChainEdge(
            source_symbol="HK.9988",
            target_symbol="HK.2331",
            relationship="commerce platforms influence brand discovery and sell-through",
            evidence="Apparel brands rely on digital traffic, promotions, and marketplace conversion.",
            risk_note="Discounting can lift sales volume while hurting margin quality.",
        ),
        ValueChainEdge(
            source_symbol="HK.3690",
            target_symbol="HK.2020",
            relationship="local-service traffic and consumer frequency indicate discretionary demand",
            evidence="Dining, travel, and retail activity can move together when confidence changes.",
            risk_note="Subsidies can make demand look stronger than underlying profitability.",
        ),
    ),
    _fixture_key("US", "defense"): (
        ValueChainEdge(
            source_symbol="LHX",
            target_symbol="LMT",
            relationship="mission systems feed prime-contractor program delivery",
            evidence="Defense primes integrate sensors, communications, and electronics from specialized suppliers.",
            risk_note="Supplier delays can create prime-contractor execution risk.",
        ),
        ValueChainEdge(
            source_symbol="HWM",
            target_symbol="RTX",
            relationship="aerospace components support engine and platform production",
            evidence="Precision components are required across aircraft and defense-system production lines.",
            risk_note="Component bottlenecks can constrain delivery schedules.",
        ),
        ValueChainEdge(
            source_symbol="LMT",
            target_symbol="NOC",
            relationship="large programs share budget, deterrence, and space-exposure themes",
            evidence="Prime contractors compete and partner across long-cycle defense priorities.",
            risk_note="Budget timing can shift revenue recognition and backlog conversion.",
        ),
        ValueChainEdge(
            source_symbol="RTX",
            target_symbol="GD",
            relationship="aerospace and defense demand link suppliers, primes, and service backlogs",
            evidence="Commercial aerospace, defense electronics, and platform production share supply-chain pressure.",
            risk_note="Commercial aerospace weakness can offset defense backlog strength.",
        ),
    ),
}
