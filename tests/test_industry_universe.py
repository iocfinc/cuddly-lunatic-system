from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quant_researcher_desk.industry_universe import (  # noqa: E402
    PlateRecord,
    build_domain_edges,
    build_industry_nodes,
    classify_domain,
    classify_gics,
    classify_value_chain_role,
    priority_rotation_nodes,
)


def test_classifies_obvious_supply_chain_industries() -> None:
    assert classify_domain("Agricultural Inputs") == "Agriculture & Food"
    assert classify_value_chain_role("Agricultural Inputs") == "upstream"
    assert classify_domain("Semiconductor Equipment & Materials") == "Industrials & Manufacturing"
    assert classify_value_chain_role("Semiconductor Equipment & Materials") == "midstream"
    assert classify_domain("Online Retailers") == "Consumer"
    assert classify_value_chain_role("Online Retailers") == "downstream"
    semis = classify_gics("Semiconductors")
    assert semis.sector == "Information Technology"
    assert semis.industry_group == "Semiconductors & Semiconductor Equipment"


def test_builds_priority_nodes_and_domain_edges() -> None:
    nodes = build_industry_nodes(
        (
            PlateRecord("US", "INDUSTRY", "US.UP", "Agricultural Inputs"),
            PlateRecord("US", "INDUSTRY", "US.MID", "Food Additives"),
            PlateRecord("US", "INDUSTRY", "US.DOWN", "Supermarkets & Convenience Stores"),
            PlateRecord("US", "CONCEPT", "US.ETF", "Broad Market ETFs"),
        )
    )

    rotation = priority_rotation_nodes(nodes)
    assert [node.gics_industry_group for node in rotation] == [
        "Consumer Staples Distribution & Retail",
        "Food, Beverage & Tobacco",
        "Materials",
    ]
    assert [node.code for node in rotation] == ["US.DOWN", "US.MID", "US.UP"]

    edges = build_domain_edges(nodes)
    assert any(edge.source_id.endswith("US.UP") for edge in edges)
