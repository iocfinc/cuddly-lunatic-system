from __future__ import annotations

import datetime as dt
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quant_researcher_desk.sector_tree import (  # noqa: E402
    CompanyProfile,
    FixtureSectorTreeProvider,
    SectorTreeError,
    SectorTreeRequest,
    ValueChainEdge,
    build_sector_tree_report,
)
from quant_researcher_desk.sector_rotation import DEFAULT_SECTOR_ROTATION, select_sector_rotation_entry  # noqa: E402


def test_build_sector_tree_report_groups_us_semiconductor_fixture() -> None:
    report = build_sector_tree_report(SectorTreeRequest(market="us", sector=" Semiconductors "))

    assert report.request.market == "US"
    assert report.request.sector == "semiconductors"
    assert [profile.symbol for profile in report.upstream] == ["AMAT", "ASML"]
    assert [profile.symbol for profile in report.midstream] == ["TSM"]
    assert [profile.symbol for profile in report.downstream] == ["AAPL", "NVDA"]
    assert [edge.source_symbol for edge in report.edges] == ["AMAT", "ASML", "TSM", "TSM"]
    assert "Upstream exposure sits with AMAT (Applied Materials), ASML (ASML Holding)." in report.educational_summary
    assert "Use this as a learning map, not as a valuation, forecast, or trading signal." in report.educational_summary


def test_hk_fixture_includes_required_report_copy() -> None:
    report = build_sector_tree_report(SectorTreeRequest(market="HK", sector="internet platforms"))

    assert [profile.symbol for profile in report.midstream] == ["HK.0700", "HK.9988"]
    assert "Sector Tree TLDR: HK Internet Platforms" in report.telegram_tldr
    assert "Main risk: HK.0981: Technology access constraints can affect node progression." in report.telegram_tldr
    assert "Educational research only, not a trading instruction." in report.telegram_tldr
    assert "compact value-chain field note across 4 companies" in report.marketing_copy


def test_hk_tech_fixture_matches_requested_sector() -> None:
    report = build_sector_tree_report(SectorTreeRequest(market="HK", sector="tech"))

    assert [profile.symbol for profile in report.upstream] == ["HK.0522", "HK.0981"]
    assert [profile.symbol for profile in report.midstream] == ["HK.0700", "HK.9988"]
    assert [profile.symbol for profile in report.downstream] == ["HK.1810", "HK.3690"]
    assert len(report.edges) == 5
    assert "HK Tech" in report.telegram_tldr


def test_rotation_entries_are_all_backed_by_sector_fixtures() -> None:
    markets = {entry.market for entry in DEFAULT_SECTOR_ROTATION}
    assert {"HK", "US"} <= markets

    for entry in DEFAULT_SECTOR_ROTATION:
        report = build_sector_tree_report(SectorTreeRequest(market=entry.market, sector=entry.sector))
        assert report.upstream
        assert report.midstream
        assert report.downstream


def test_select_sector_rotation_entry_is_date_deterministic() -> None:
    entry = select_sector_rotation_entry(current_date=dt.date(2026, 4, 29))
    assert entry in DEFAULT_SECTOR_ROTATION


def test_focus_symbols_filters_profiles_and_edges_deterministically() -> None:
    report = build_sector_tree_report(
        SectorTreeRequest(
            market="US",
            sector="semiconductors",
            focus_symbols=("nvda", "tsm", "asml", "tsm"),
        )
    )

    assert report.request.focus_symbols == ("ASML", "NVDA", "TSM")
    assert [profile.symbol for profile in report.upstream] == ["ASML"]
    assert [profile.symbol for profile in report.midstream] == ["TSM"]
    assert [profile.symbol for profile in report.downstream] == ["NVDA"]
    assert [(edge.source_symbol, edge.target_symbol) for edge in report.edges] == [
        ("ASML", "TSM"),
        ("TSM", "NVDA"),
    ]


def test_max_companies_per_group_limits_each_group_without_changing_request() -> None:
    report = build_sector_tree_report(
        SectorTreeRequest(market="US", sector="semiconductors", max_companies_per_group=1)
    )

    assert [profile.symbol for profile in report.upstream] == ["AMAT"]
    assert [profile.symbol for profile in report.downstream] == ["AAPL"]
    assert [(edge.source_symbol, edge.target_symbol) for edge in report.edges] == [
        ("AMAT", "TSM"),
        ("TSM", "AAPL"),
    ]
    assert not any(risk.startswith("ASML:") or risk.startswith("NVDA:") for risk in report.risks)
    assert report.request.max_companies_per_group == 1


def test_custom_provider_can_supply_profiles_and_edges() -> None:
    provider = FixtureSectorTreeProvider(
        profiles={
            ("US", "software"): (
                CompanyProfile(
                    symbol="DB",
                    name="Data Builder",
                    market="US",
                    sector="software",
                    industry="Infrastructure software",
                    value_chain_role="upstream",
                    business_summary="Provides developer data tooling.",
                    key_risks=("Usage-based revenue can be volatile.",),
                ),
                CompanyProfile(
                    symbol="APP",
                    name="Application Layer",
                    market="US",
                    sector="software",
                    industry="Application software",
                    value_chain_role="downstream",
                    business_summary="Packages infrastructure into end-user workflows.",
                    key_risks=("Seat expansion can slow during budget reviews.",),
                ),
            )
        },
        edges={
            ("US", "software"): (
                ValueChainEdge(
                    source_symbol="DB",
                    target_symbol="APP",
                    relationship="developer data platform supports application workflows",
                    evidence="Applications can depend on database and data-pipeline layers.",
                    risk_note="Infrastructure outages can affect application reliability.",
                ),
            )
        },
    )

    report = build_sector_tree_report(SectorTreeRequest(market="US", sector="software"), provider)

    assert [profile.symbol for profile in report.upstream] == ["DB"]
    assert [profile.symbol for profile in report.downstream] == ["APP"]
    assert report.edges[0].relationship == "developer data platform supports application workflows"
    assert "DB->APP: Infrastructure outages can affect application reliability." in report.risks


def test_unknown_fixture_raises_clear_error() -> None:
    with pytest.raises(SectorTreeError, match="No fixture data found for US utilities"):
        build_sector_tree_report(SectorTreeRequest(market="US", sector="utilities"))


def test_invalid_request_and_invalid_role_raise_clear_errors() -> None:
    with pytest.raises(SectorTreeError, match="Market is required"):
        build_sector_tree_report(SectorTreeRequest(market=" ", sector="semiconductors"))

    provider = FixtureSectorTreeProvider(
        profiles={
            ("US", "broken"): (
                CompanyProfile(
                    symbol="BAD",
                    name="Bad Role",
                    market="US",
                    sector="broken",
                    industry="Broken data",
                    value_chain_role="producer",
                    business_summary="Invalid fixture.",
                ),
            )
        },
        edges={("US", "broken"): ()},
    )
    with pytest.raises(SectorTreeError, match="Unsupported value-chain role for BAD"):
        build_sector_tree_report(SectorTreeRequest(market="US", sector="broken"), provider)
