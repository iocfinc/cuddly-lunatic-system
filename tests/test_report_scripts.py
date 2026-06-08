from __future__ import annotations

import pathlib
import subprocess
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]


def run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
    )


def test_options_research_script_fixture_dry_run_writes_attachment(tmp_path: pathlib.Path) -> None:
    result = run_script(
        "scripts/send_options_research_report.py",
        "--dry-run",
        "--fixture",
        "--symbol",
        "US.TEST",
        "--report-format",
        "html",
        "--output-dir",
        str(tmp_path),
    )

    assert result.returncode == 0, result.stderr
    assert "US.TEST Options Desk Note" in result.stdout
    assert "attachment:" in result.stdout
    files = list(tmp_path.glob("*.html"))
    assert files
    assert files[0].name.startswith("us-test-options-research")


def test_options_research_script_visual_explainer_writes_html_with_visual_sections(tmp_path: pathlib.Path) -> None:
    result = run_script(
        "scripts/send_options_research_report.py",
        "--dry-run",
        "--fixture",
        "--symbol",
        "US.TEST",
        "--visual-explainer",
        "--report-format",
        "html",
        "--output-dir",
        str(tmp_path),
    )

    assert result.returncode == 0, result.stderr
    files = list(tmp_path.glob("*.html"))
    assert files
    html = files[0].read_text(encoding="utf-8")
    assert "Black-Scholes Value Curve" in html
    assert "Monte Carlo Sample Paths" in html


def test_options_research_script_shadow_compare_writes_migration_check(tmp_path: pathlib.Path) -> None:
    result = run_script(
        "scripts/send_options_research_report.py",
        "--dry-run",
        "--fixture",
        "--symbol",
        "US.TEST",
        "--shadow-compare",
        "--report-format",
        "html",
        "--output-dir",
        str(tmp_path),
    )

    assert result.returncode == 0, result.stderr
    files = list(tmp_path.glob("*.html"))
    assert files
    html = files[0].read_text(encoding="utf-8")
    assert "Pricing Engine Migration Check" in html
    assert "Pricing Engine" in html


def test_sector_tree_script_fixture_dry_run_writes_attachment(tmp_path: pathlib.Path) -> None:
    result = run_script(
        "scripts/send_sector_tree_report.py",
        "--dry-run",
        "--market",
        "HK",
        "--sector",
        "internet platforms",
        "--report-format",
        "html",
        "--output-dir",
        str(tmp_path),
    )

    assert result.returncode == 0, result.stderr
    assert "HK Internet Platforms" in result.stdout
    assert "attachment:" in result.stdout
    files = list(tmp_path.glob("*.html"))
    assert files
    assert files[0].name == "hk-internet-platforms-sector-map.html"


def test_sector_tree_script_rotation_selects_supported_sector(tmp_path: pathlib.Path) -> None:
    result = run_script(
        "scripts/send_sector_tree_report.py",
        "--dry-run",
        "--rotate",
        "--report-format",
        "html",
        "--output-dir",
        str(tmp_path),
    )

    assert result.returncode == 0, result.stderr
    assert "sector rotation selected:" in result.stdout
    assert "attachment:" in result.stdout
    assert list(tmp_path.glob("*.html"))


def test_hk_finance_power_map_script_fixture_dry_run_writes_attachment(tmp_path: pathlib.Path) -> None:
    result = run_script(
        "scripts/send_hk_sector_power_map.py",
        "--dry-run",
        "--market",
        "HK",
        "--sector",
        "finance",
        "--report-format",
        "html",
        "--output-dir",
        str(tmp_path),
    )

    assert result.returncode == 0, result.stderr
    assert "HK Finance Breadth-First Power Map" in result.stdout
    assert "attachment:" in result.stdout
    files = list(tmp_path.glob("*.html"))
    assert files
    assert files[0].name == "hk-finance-breadth-first-power-map.html"


def test_tradingagents_packet_script_fixture_dry_run_writes_attachment_and_json(tmp_path: pathlib.Path) -> None:
    result = run_script(
        "scripts/send_tradingagents_packet.py",
        "--dry-run",
        "--fixture",
        "--symbol",
        "US.TEST",
        "--report-format",
        "html",
        "--output-dir",
        str(tmp_path),
        "--results-dir",
        str(tmp_path / "results"),
    )

    assert result.returncode == 0, result.stderr
    assert "US.TEST Decision Packet" in result.stdout
    assert "attachment:" in result.stdout
    assert "artifact:" in result.stdout
    assert list(tmp_path.glob("*.html"))
    assert list((tmp_path / "results").rglob("*.json"))


def test_tradingagents_packet_script_live_path_fails_gracefully_when_disabled(tmp_path: pathlib.Path) -> None:
    result = run_script(
        "scripts/send_tradingagents_packet.py",
        "--dry-run",
        "--symbol",
        "US.TEST",
        "--report-format",
        "html",
        "--output-dir",
        str(tmp_path),
    )

    assert result.returncode == 1
    assert (
        "TRADINGAGENTS_ENABLED=true" in result.stderr
        or "Cannot connect to OpenD" in result.stderr
    )


def test_tradingagents_packet_script_reports_typed_single_symbol_optionability_failure(tmp_path: pathlib.Path) -> None:
    result = run_script(
        "scripts/send_tradingagents_packet.py",
        "--dry-run",
        "--fixture",
        "--symbol",
        "US.NOOPT",
        "--report-format",
        "html",
        "--output-dir",
        str(tmp_path),
        "--results-dir",
        str(tmp_path / "results"),
    )

    assert result.returncode == 1
    assert "option chain returned no usable rows" in result.stderr
    assert "stage=evidence_pack" in result.stderr


def test_tradingagents_watchlist_digest_script_fixture_dry_run_writes_attachment(tmp_path: pathlib.Path) -> None:
    result = run_script(
        "scripts/send_tradingagents_watchlist_digest.py",
        "--dry-run",
        "--fixture",
        "--symbols",
        "US.NVDA,US.NOOPT,US.TSM",
        "--report-format",
        "html",
        "--output-dir",
        str(tmp_path),
    )

    assert result.returncode == 0, result.stderr
    assert "TradingAgents Watchlist Digest" in result.stdout
    assert "attachment:" in result.stdout
    assert "summary:" in result.stdout
    assert list(tmp_path.glob("*.html"))
    assert list(tmp_path.glob("*-summary.json"))


def test_weekly_options_packet_script_fixture_dry_run_writes_pdf_bundle(tmp_path: pathlib.Path) -> None:
    result = run_script(
        "scripts/send_weekly_options_packet.py",
        "--dry-run",
        "--fixture",
        "--report-format",
        "pdf",
        "--top-n",
        "4",
        "--output-dir",
        str(tmp_path),
    )

    assert result.returncode == 0, result.stderr
    assert "US Weekly Options Packet" in result.stdout
    assert "attachment:" in result.stdout
    assert list(tmp_path.glob("*.pdf"))


def test_supply_chain_mapper_script_dry_run_writes_explorer_and_manifest(tmp_path: pathlib.Path) -> None:
    import pytest

    corpus_path = ROOT / "data" / "supply-chain-mapper" / "pilot_corpus" / "tsmc-fab-output.json"
    if not corpus_path.exists():
        pytest.skip("requires local supply-chain corpus fixture that is intentionally not committed")

    result = run_script(
        "scripts/build_supply_chain_map.py",
        "--artifact",
        "tsmc-fab-output",
        "--output-root",
        str(tmp_path),
    )

    assert result.returncode == 0, result.stderr
    assert "TSMC Leading-Edge Fab Output" in result.stdout
    assert "explorer:" in result.stdout
    assert "manifest:" in result.stdout
    assert "audit:" in result.stdout
    assert "stress:" in result.stdout
    assert list(tmp_path.rglob("*explorer.html"))
    assert list(tmp_path.rglob("manifest.json"))
