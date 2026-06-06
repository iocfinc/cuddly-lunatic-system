from __future__ import annotations

import builtins
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quant_researcher_desk.reporting import (  # noqa: E402
    ReportRenderError,
    render_image_report,
    render_pdf_report,
    render_report_html,
    write_native_pdf_report,
    write_html_report,
)


def sample_sections() -> list[dict[str, object]]:
    return [
        {
            "title": "Market Setup",
            "summary": "Statement. Evidence. Interpretation. Risk.",
            "items": ["Liquidity concentrated near front-week strikes.", "Scenario paths remain asymmetric."],
        },
        {
            "title": "Sector Table",
            "table": {
                "columns": ["sector", "signal", "risk"],
                "rows": [["Semis", "Vol bid", "Gap risk"], ["Energy", "Range", "Macro headline"]],
            },
        },
        {
            "title": "Relationship Map",
            "relationship_map": {
                "columns": [
                    {"label": "Upstream", "items": [{"symbol": "ASML", "name": "ASML Holding", "industry": "Equipment"}]},
                    {"label": "Midstream", "items": [{"symbol": "TSM", "name": "Taiwan Semiconductor", "industry": "Foundry"}]},
                    {"label": "Downstream", "items": [{"symbol": "NVDA", "name": "NVIDIA", "industry": "Accelerated computing"}]},
                ],
                "edges": [{"source": "ASML", "target": "TSM", "relationship": "enables manufacturing"}],
            },
        },
    ]


def test_render_report_html_escapes_text_and_renders_institutional_template() -> None:
    html = render_report_html(
        "TSM <Options>",
        sample_sections(),
        {"generated_at": "2026-04-28", "analyst": "Research & Risk"},
    )

    assert "<!doctype html>" in html
    assert "Quant Researcher Desk" in html
    assert "TSM &lt;Options&gt;" in html
    assert "Research &amp; Risk" in html
    assert "metadata-grid" in html
    assert "report-section" in html
    assert "size: A4" in html
    assert "relationship-map" in html
    assert "ASML -> TSM" in html
    assert "<th>Sector</th>" in html
    assert "Semis" in html


def test_render_report_html_supports_infographic_bar_charts() -> None:
    html = render_report_html(
        "Scenario Card",
        [{"title": "Scenario Shape", "chart": {"rows": [{"label": "-5%", "value": -1.2}, {"label": "+5%", "value": 2.4}]}}],
        {"symbol": "US.TSM"},
    )

    assert "bar-chart" in html
    assert "chart-bar negative" in html
    assert "chart-bar positive" in html
    assert "-5%" in html


def test_render_report_html_supports_line_charts_and_multi_series() -> None:
    html = render_report_html(
        "Pricing Curves",
        [
            {
                "title": "Black-Scholes Value Curve",
                "chart": {
                    "type": "line",
                    "rows": [
                        {"label": "380", "value": 2.1},
                        {"label": "390", "value": 4.3},
                        {"label": "400", "value": 7.2},
                    ],
                },
            },
            {
                "title": "Monte Carlo Sample Paths",
                "chart": {
                    "type": "line",
                    "series": [
                        {"label": "Path 1", "rows": [{"label": "0d", "value": 395.0}, {"label": "7d", "value": 389.5}]},
                        {"label": "Path 2", "rows": [{"label": "0d", "value": 395.0}, {"label": "7d", "value": 401.2}]},
                    ],
                },
            },
        ],
        {"symbol": "US.TEST"},
    )

    assert "line-chart" in html
    assert "line-chart-svg" in html
    assert "series-label" in html
    assert "Path 1" in html


def test_write_html_report_creates_parent_directory(tmp_path: pathlib.Path) -> None:
    output_path = tmp_path / "reports" / "daily.html"

    written_path = write_html_report("Daily Desk", sample_sections(), {"symbol": "US.TSM"}, output_path)

    assert written_path == output_path
    assert output_path.exists()
    assert "Daily Desk" in output_path.read_text(encoding="utf-8")


def test_render_pdf_report_writes_native_pdf_when_playwright_is_unavailable(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):  # type: ignore[no-untyped-def]
        if name == "playwright.sync_api":
            raise ModuleNotFoundError("No module named 'playwright'")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    pdf_path = tmp_path / "daily.pdf"

    rendered_path = render_pdf_report("Daily Desk", sample_sections(), {"symbol": "US.TSM"}, pdf_path)

    assert rendered_path == pdf_path
    assert pdf_path.read_bytes().startswith(b"%PDF-1.4")
    assert not (tmp_path / "daily.html").exists()


def test_write_native_pdf_report_creates_pdf_file(tmp_path: pathlib.Path) -> None:
    pdf_path = tmp_path / "native.pdf"

    rendered = write_native_pdf_report("Native Desk", sample_sections(), {"symbol": "US.TSM"}, pdf_path)

    assert rendered == pdf_path
    pdf_bytes = pdf_path.read_bytes()
    assert pdf_bytes.startswith(b"%PDF-1.4")
    assert b"/MediaBox [0 0 595 842]" in pdf_bytes


def test_render_image_report_does_not_launch_system_chrome_when_playwright_is_unavailable(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):  # type: ignore[no-untyped-def]
        if name == "playwright.sync_api":
            raise ModuleNotFoundError("No module named 'playwright'")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    image_path = tmp_path / "daily.png"

    with pytest.raises(ReportRenderError, match="System Chrome was not launched"):
        render_image_report("Daily Desk", sample_sections(), {"symbol": "US.TSM"}, image_path)

    assert (tmp_path / "daily.html").exists()
    assert not image_path.exists()
