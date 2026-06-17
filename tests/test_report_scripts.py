from __future__ import annotations

import json
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
        "--opend-port",
        "9",
    )

    assert result.returncode == 0, result.stderr
    assert "US.TEST Options Desk Note" in result.stdout
    assert "attachment:" in result.stdout
    files = list(tmp_path.glob("*.html"))
    assert files
    assert files[0].name.startswith("us-test-options-research")


def test_tsmc_options_script_fixture_dry_run_prints_report() -> None:
    result = run_script(
        "scripts/send_tsmc_options_report.py",
        "--dry-run",
        "--fixture",
        "--symbol",
        "US.TSM",
        "--rows",
        "2",
    )

    assert result.returncode == 0, result.stderr
    assert "Quant Researcher Desk - US.TSM Options" in result.stdout
    assert "Selected expiry:" in result.stdout
    assert "Scanned contracts:" in result.stdout


def test_tsmc_options_script_reports_exact_opend_blocker() -> None:
    result = run_script(
        "scripts/send_tsmc_options_report.py",
        "--dry-run",
        "--symbol",
        "US.TSM",
        "--opend-port",
        "9",
    )

    expected = "moomoo options report failed: Cannot connect to OpenD at 127.0.0.1:9. Start and log into OpenD first."
    assert result.returncode == 1
    assert expected in result.stderr


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
        "--opend-port",
        "9",
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


def test_options_research_script_strategy_gate_writes_comparison_section(tmp_path: pathlib.Path) -> None:
    result = run_script(
        "scripts/send_options_research_report.py",
        "--dry-run",
        "--fixture",
        "--symbol",
        "US.TEST",
        "--strategy-gate-passed",
        "--strategy-gate-reason",
        "fixture stock-first gate passed",
        "--report-format",
        "html",
        "--output-dir",
        str(tmp_path),
    )

    assert result.returncode == 0, result.stderr
    files = list(tmp_path.glob("*.html"))
    assert files
    html = files[0].read_text(encoding="utf-8")
    assert "Post-Gate Strategy Comparison" in html
    assert "fixture stock-first gate passed" in html
    assert "not execution instructions" in html


def test_options_research_script_persists_journal_without_posting(tmp_path: pathlib.Path) -> None:
    journal_dir = tmp_path / "journal"
    result = run_script(
        "scripts/send_options_research_report.py",
        "--dry-run",
        "--fixture",
        "--symbol",
        "US.TEST",
        "--persist-journal",
        "--journal-dir",
        str(journal_dir),
        "--report-format",
        "html",
        "--output-dir",
        str(tmp_path / "reports"),
    )

    assert result.returncode == 0, result.stderr
    assert "journal:" in result.stdout
    assert "telegram report sent" not in result.stdout
    journal_path = journal_dir / "options-journal.json"
    payload = json.loads(journal_path.read_text(encoding="utf-8"))
    assert len(payload) == 1
    assert payload[0]["symbol"] == "US.TEST"
    assert payload[0]["report_path"].endswith(".html")


def test_update_options_journal_script_updates_existing_entry(tmp_path: pathlib.Path) -> None:
    journal_dir = tmp_path / "journal"
    create_result = run_script(
        "scripts/send_options_research_report.py",
        "--dry-run",
        "--fixture",
        "--symbol",
        "US.TEST",
        "--persist-journal",
        "--journal-dir",
        str(journal_dir),
        "--report-format",
        "html",
        "--output-dir",
        str(tmp_path / "reports"),
    )
    assert create_result.returncode == 0, create_result.stderr
    journal_line = next(line for line in create_result.stdout.splitlines() if line.startswith("journal: "))
    entry_id = journal_line.rsplit("#", 1)[1]

    update_result = run_script(
        "scripts/update_options_journal.py",
        "--journal-dir",
        str(journal_dir),
        "--entry-id",
        entry_id,
        "--status",
        "inconclusive",
        "--lesson",
        "Outcome stayed mixed after the planned review window.",
        "--underlying-price",
        "101.5",
        "--option-price",
        "3.9",
        "--updated-at",
        "2026-05-02T12:00:00+00:00",
    )

    assert update_result.returncode == 0, update_result.stderr
    payload = json.loads((journal_dir / "options-journal.json").read_text(encoding="utf-8"))
    assert payload[0]["outcome"]["status"] == "inconclusive"
    assert payload[0]["outcome"]["underlying_price"] == 101.5
    assert "mixed" in payload[0]["outcome"]["lesson"]


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
        "--opend-port",
        "9",
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


def test_catalyst_options_review_script_fixture_run_writes_report_and_passes_advisor(tmp_path: pathlib.Path) -> None:
    result = run_script(
        "scripts/run_catalyst_options_review.py",
        "--dry-run",
        "--fixture",
        "--output-dir",
        str(tmp_path),
    )

    assert result.returncode == 0, result.stderr
    assert "Catalyst Options Review" in result.stdout
    assert "advisor-verdict: PASS" in result.stdout
    assert "screen-json:" in result.stdout
    assert "report-pdf:" in result.stdout
    assert list(tmp_path.glob("*-catalyst-options-review.json"))
    assert list(tmp_path.glob("*-catalyst-options-review.html"))
    assert list(tmp_path.glob("*-catalyst-options-review.pdf"))


def test_catalyst_options_screen_script_records_fixture_run_provenance(tmp_path: pathlib.Path) -> None:
    ledger_path = tmp_path / "run-ledger.jsonl"
    result = run_script(
        "scripts/send_catalyst_options_screen.py",
        "--dry-run",
        "--fixture",
        "--skip-telegram",
        "--output-dir",
        str(tmp_path),
        "--run-ledger",
        str(ledger_path),
    )

    assert result.returncode == 0, result.stderr
    assert "Catalyst Options Screen" in result.stdout
    assert "attachment:" in result.stdout
    assert (tmp_path / "catalyst-options-screen.pdf").exists()

    entries = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["status"] == "succeeded"
    assert entry["mode"] == "dry-run"
    assert "scripts/send_catalyst_options_screen.py" in entry["command_shape"]
    assert entry["output_dir"] == str(tmp_path)
    assert entry["artifact_path"] == str(tmp_path / "catalyst-options-screen.pdf")
    assert entry["timestamp"]
    assert entry["blocker"] is None


def test_catalyst_options_screen_script_records_exact_opend_blocker(tmp_path: pathlib.Path) -> None:
    ledger_path = tmp_path / "run-ledger.jsonl"
    result = run_script(
        "scripts/send_catalyst_options_screen.py",
        "--dry-run",
        "--output-dir",
        str(tmp_path),
        "--run-ledger",
        str(ledger_path),
        "--opend-port",
        "9",
    )

    expected = "catalyst options screen failed: Cannot connect to OpenD at 127.0.0.1:9. Start and log into OpenD first."
    assert result.returncode == 1
    assert expected in result.stderr

    entries = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["status"] == "failed"
    assert entry["mode"] == "dry-run"
    assert entry["artifact_path"] is None
    assert entry["blocker"] == expected


def test_catalyst_options_screen_script_records_telegram_disabled_skip_without_success(tmp_path: pathlib.Path) -> None:
    ledger_path = tmp_path / "run-ledger.jsonl"
    result = run_script(
        "scripts/send_catalyst_options_screen.py",
        "--post",
        "--fixture",
        "--skip-telegram",
        "--output-dir",
        str(tmp_path),
        "--run-ledger",
        str(ledger_path),
    )

    expected = "telegram notification skipped: --skip-telegram was set"
    assert result.returncode == 0, result.stderr
    assert expected in result.stdout
    assert "telegram report sent" not in result.stdout

    entries = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["status"] == "skipped"
    assert entry["mode"] == "post"
    assert entry["artifact_path"] == str(tmp_path / "catalyst-options-screen.pdf")
    assert entry["blocker"] == expected


def test_cron_options_update_records_durable_run_ledger_contract() -> None:
    script = (ROOT / "scripts" / "cron_options_update.sh").read_text(encoding="utf-8")

    assert 'STATE_DIR="$ROOT/reports/run-state"' in script
    assert 'RUN_LEDGER="$STATE_DIR/options-update-ledger.jsonl"' in script
    assert 'ARTIFACT_PATH="$ROOT/reports/catalyst-options/catalyst-options-screen.pdf"' in script
    assert "record_run" in script
    assert 'record_run "skipped_lock_active" 0' in script
    assert '--run-ledger "$RUN_LEDGER"' in script


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
