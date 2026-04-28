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
    assert files[0].name == "hk-internet-platforms-sector-tree.html"


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
