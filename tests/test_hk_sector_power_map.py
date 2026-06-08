from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quant_researcher_desk.hk_sector_power_map import (  # noqa: E402
    FinancePowerMapError,
    FinancePowerMapRequest,
    build_hk_finance_power_map_report,
    finance_power_map_sections,
    format_hk_finance_telegram_html,
)


def test_build_hk_finance_power_map_report_groups_nodes_and_edges() -> None:
    report = build_hk_finance_power_map_report(FinancePowerMapRequest(market="HK", sector="finance"))

    assert [node.symbol for node in report.upstream] == ["HK.LIST1079", "HK.LIST1003"]
    assert [node.symbol for node in report.midstream] == ["HK.LIST1030", "HK.LIST1007", "HK.LIST1068"]
    assert [node.symbol for node in report.downstream] == ["HK.LIST1004", "HK.LIST23362", "HK.LIST1311"]
    assert len(report.edges) == 8
    assert "breadth-first reference network" in report.thesis
    assert "Learning Corner:" in report.learning_corner
    assert "Research only, not a trading instruction." in report.telegram_tldr


def test_finance_power_map_sections_include_map_and_tables() -> None:
    report = build_hk_finance_power_map_report()
    sections = finance_power_map_sections(report)

    assert [section["title"] for section in sections] == [
        "Power Thesis",
        "Breadth-First Map",
        "Sector Matrix",
        "Relationship Edges",
        "Learning Corner",
        "Telegram TLDR",
    ]
    assert "relationship_map" in sections[1]
    assert "table" in sections[2]
    assert "table" in sections[3]


def test_format_hk_finance_telegram_html_includes_one_pager_copy() -> None:
    report = build_hk_finance_power_map_report()
    caption = format_hk_finance_telegram_html(report)

    assert "HK Finance Breadth-First Power Map" in caption
    assert "Upstream:" in caption
    assert "PDF attached." in caption
    assert "Research only, not a trading instruction." in caption


def test_invalid_market_and_sector_raise_clear_errors() -> None:
    with pytest.raises(FinancePowerMapError, match="Only HK market coverage"):
        build_hk_finance_power_map_report(FinancePowerMapRequest(market="US", sector="finance"))

    with pytest.raises(FinancePowerMapError, match="Only HK finance"):
        build_hk_finance_power_map_report(FinancePowerMapRequest(market="HK", sector="consumer-services"))

