"""Weekly options packet builder with overview pages and fixed-layout tear sheets."""

from __future__ import annotations

import datetime as dt
import html
import json
import os
import pathlib
import subprocess
import tempfile
import time
from dataclasses import dataclass, replace
from typing import Any

from quant_researcher_desk.execution_recovery import REASON_PROVIDER_RATE_LIMITED, normalize_options_report_error
from quant_researcher_desk.moomoo_options_report import OptionsReportError
from quant_researcher_desk.options_research import (
    FixtureOptionsResearchProvider,
    OptionsResearchReport,
    OptionsResearchRequest,
    build_options_research_report,
)
from quant_researcher_desk.reporting import ReportRenderError, render_html_file_to_pdf_with_chrome, write_native_pdf_report
from quant_researcher_desk.weekly_agent_review import (
    WeeklyAgentReviewConfig,
    WeeklyAgentReviewResult,
    load_weekly_agent_review_config,
    maybe_request_weekly_agent_review,
)
from quant_researcher_desk.weekly_options_screener import WeeklyScreenResult, shortlist_rows


@dataclass(frozen=True)
class WriterCopy:
    executive_summary: str
    contract_takeaway: str
    action_items: list[str]
    risk_callouts: list[str]
    questions_to_verify: list[str]


@dataclass(frozen=True)
class WeeklyOptionsTearSheet:
    rank: int
    report: OptionsResearchReport
    writer_copy: WriterCopy

    @property
    def contract(self):  # type: ignore[no-untyped-def]
        return self.report.contract


@dataclass(frozen=True)
class WeeklyOptionsPacket:
    title: str
    generated_at: dt.datetime
    weekly_result: WeeklyScreenResult
    executive_summary: str
    methodology_summary: str
    tearsheets: tuple[WeeklyOptionsTearSheet, ...]
    agent_review: WeeklyAgentReviewResult | None = None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class OptionsReportWriterConfig:
    enabled: bool
    codex_model: str
    codex_profile: str | None


def load_options_report_writer_config(env: dict[str, str] | None = None) -> OptionsReportWriterConfig:
    values = env or os.environ
    return OptionsReportWriterConfig(
        enabled=values.get("OPTIONS_REPORT_WRITER_ENABLED", "false").lower() == "true",
        codex_model=values.get("OPTIONS_REPORT_WRITER_MODEL", "gpt-5.4-mini"),
        codex_profile=values.get("OPTIONS_REPORT_WRITER_PROFILE", "options_report_writer"),
    )


def _writer_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "executive_summary": {"type": "string"},
            "contract_takeaway": {"type": "string"},
            "action_items": {"type": "array", "items": {"type": "string"}},
            "risk_callouts": {"type": "array", "items": {"type": "string"}},
            "questions_to_verify": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "executive_summary",
            "contract_takeaway",
            "action_items",
            "risk_callouts",
            "questions_to_verify",
        ],
    }


def _fallback_writer_copy(report: OptionsResearchReport, rank: int) -> WriterCopy:
    return WriterCopy(
        executive_summary=(
            f"Rank {rank} is {report.contract.code}. It reads as {report.verdict.lower()} with a "
            f"{report.valuation_view.lower()} valuation view and a fair value gap of {report.fair_value_gap_pct:.1%}."
        ),
        contract_takeaway=(
            f"{report.contract.code} is useful as a tear sheet because strike, premium, IV/HV, and scenario shape can be reviewed together. "
            f"The current premium looks {report.valuation_view.lower()} versus the blended model estimate."
        ),
        action_items=[
            "Check spread width before acting on the screen.",
            "Review catalyst timing and earnings proximity against the expiry.",
            "Confirm whether the valuation view still holds after intraday repricing.",
        ],
        risk_callouts=list(report.risks),
        questions_to_verify=[
            "Is the premium still rich/near fair/cheap after the latest quote refresh?",
            "Does open interest stay deep enough at the selected strike?",
            "Is there an event or headline that invalidates a pure model read?",
        ],
    )


def _writer_prompt(report: OptionsResearchReport, rank: int) -> str:
    return f"""You are packaging an options research tear sheet.

Return JSON only.

Selected contract:
- rank: {rank}
- symbol: {report.symbol}
- contract: {report.contract.code}
- strike: {report.contract.strike}
- expiry: {report.contract.expiry}
- premium: {report.contract.market_price}
- underlying: {report.underlying_price}
- valuation_view: {report.valuation_view}
- fair_value_gap_pct: {report.fair_value_gap_pct:.4f}
- verdict: {report.verdict}
- iv: {report.implied_volatility_used:.4f}
- hv: {report.historical_volatility:.4f}

Write concise, research-first copy. No hype. No execution language.
"""


def _codex_writer_copy(report: OptionsResearchReport, rank: int, config: OptionsReportWriterConfig) -> WriterCopy:
    with tempfile.TemporaryDirectory(prefix="options-writer-") as tmp_dir:
        tmp_path = pathlib.Path(tmp_dir)
        schema_path = tmp_path / "schema.json"
        output_path = tmp_path / "last-message.json"
        schema_path.write_text(json.dumps(_writer_output_schema(), indent=2), encoding="utf-8")
        cmd = [
            "codex",
            "exec",
            "-m",
            config.codex_model,
            "-C",
            str(pathlib.Path(__file__).resolve().parents[2]),
            "--sandbox",
            "read-only",
            "--output-schema",
            str(schema_path),
            "-o",
            str(output_path),
            "-",
        ]
        if config.codex_profile:
            cmd[2:2] = ["-p", config.codex_profile]
        subprocess.run(
            cmd,
            input=_writer_prompt(report, rank),
            text=True,
            capture_output=True,
            check=True,
            cwd=str(pathlib.Path(__file__).resolve().parents[2]),
            env=dict(os.environ),
        )
        payload = json.loads(output_path.read_text(encoding="utf-8"))
    return WriterCopy(
        executive_summary=str(payload["executive_summary"]),
        contract_takeaway=str(payload["contract_takeaway"]),
        action_items=[str(item) for item in payload["action_items"]],
        risk_callouts=[str(item) for item in payload["risk_callouts"]],
        questions_to_verify=[str(item) for item in payload["questions_to_verify"]],
    )


def _build_tearsheet_report_with_recovery(
    provider: Any,
    request: OptionsResearchRequest,
    *,
    now: dt.datetime,
    max_attempts: int = 3,
    cooldown_seconds: float = 30.0,
) -> OptionsResearchReport:
    attempts = 0
    while True:
        attempts += 1
        try:
            return build_options_research_report(provider, request, now=now)
        except OptionsReportError as exc:
            issue = normalize_options_report_error(request.symbol, "tearsheet_report", exc)
            if issue.reason_code != REASON_PROVIDER_RATE_LIMITED or attempts >= max_attempts:
                raise
            time.sleep(cooldown_seconds)


def build_weekly_options_packet(
    weekly_result: WeeklyScreenResult,
    provider: Any,
    *,
    now: dt.datetime | None = None,
    writer_config: OptionsReportWriterConfig | None = None,
    agent_review_config: WeeklyAgentReviewConfig | None = None,
) -> WeeklyOptionsPacket:
    current = now or weekly_result.generated_at
    writer = writer_config or load_options_report_writer_config()
    agent_reviewer = agent_review_config or load_weekly_agent_review_config()
    tearsheets: list[WeeklyOptionsTearSheet] = []
    for rank, option in enumerate(weekly_result.ranked_options, start=1):
        report = _build_tearsheet_report_with_recovery(
            provider,
            OptionsResearchRequest(
                symbol=option.symbol,
                option_code=option.option_code,
                option_type=option.side,
                expiry=option.expiry,
                historical_volatility=weekly_result.request.historical_volatility,
                pricing_engine=weekly_result.pricing_engine,
                shadow_compare=weekly_result.shadow_compare,
            ),
            now=current,
        )
        if writer.enabled:
            try:
                copy = _codex_writer_copy(report, rank, writer)
            except (subprocess.SubprocessError, FileNotFoundError, json.JSONDecodeError):
                copy = _fallback_writer_copy(report, rank)
        else:
            copy = _fallback_writer_copy(report, rank)
        tearsheets.append(WeeklyOptionsTearSheet(rank=rank, report=report, writer_copy=copy))

    found = len(weekly_result.ranked_options)
    target = weekly_result.request.top_n
    executive_summary = (
        f"This packet covers the weekly {weekly_result.request.market} options screen for {current.date().isoformat()}. "
        f"It found {found} contracts under the current strict rules out of a target shortlist of {target}. "
        f"Composite score is a review-priority signal; valuation view explains whether the premium looks cheap, near fair, or rich. "
        f"The active pricing engine is {weekly_result.pricing_engine}."
    )
    if weekly_result.review_summary:
        executive_summary += f" Reviewer lane: {weekly_result.review_summary}"
    methodology_summary = (
        "This is a stock-first weekly packet: start with stock context, confirm the trend regime and direction, then use each tear sheet as a contract-level review artifact. "
        "Strike is the exercise reference price, premium is the current contract price, and fair value gap compares blended model value against that premium."
    )
    packet = WeeklyOptionsPacket(
        title=f"{weekly_result.request.market} Weekly Options Packet",
        generated_at=current,
        weekly_result=weekly_result,
        executive_summary=executive_summary,
        methodology_summary=methodology_summary,
        tearsheets=tuple(tearsheets),
    )
    agent_review, warnings = maybe_request_weekly_agent_review(packet, agent_reviewer)
    if agent_review is None and warnings:
        packet = replace(
            packet,
            executive_summary=f"{packet.executive_summary} Agent Review warning: {warnings[-1]}",
            warnings=tuple(warnings),
        )
    elif warnings:
        packet = replace(packet, warnings=tuple(warnings))
    if agent_review is not None:
        packet = replace(packet, agent_review=agent_review)
    return packet


def _escape(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _svg_bar_chart(rows: list[dict[str, float | str]], color: str) -> str:
    width = 620
    height = 220
    if not rows:
        return '<div class="chart-empty">No data available.</div>'
    values = [float(row["value"]) for row in rows]
    min_value = min(values)
    max_value = max(values)
    span = max(max_value - min_value, 0.01)
    if min_value < 0 < max_value:
        baseline = 170 - ((0 - min_value) / span) * 150
    elif min_value >= 0:
        baseline = 170
    else:
        baseline = 20
    bar_width = max(width // max(len(rows), 1), 28)
    bars = []
    for index, row in enumerate(rows):
        value = float(row["value"])
        scaled_height = max(8, abs(value) / max(abs(min_value), abs(max_value), 0.01) * 150)
        x = 18 + index * bar_width
        y = baseline - scaled_height if value >= 0 else baseline
        bars.append(f'<rect x="{x}" y="{y:.1f}" width="{bar_width - 8}" height="{scaled_height:.1f}" rx="4" fill="{color}" />')
        bars.append(f'<text x="{x + (bar_width - 8) / 2:.1f}" y="188" text-anchor="middle" class="axis">{_escape(row["label"])}</text>')
    zero_line = f'<line x1="12" y1="{baseline:.1f}" x2="{width - 12}" y2="{baseline:.1f}" stroke="#5e5651" stroke-width="1.5" />'
    return f'<svg viewBox="0 0 {width} {height}" class="chart-svg">{zero_line}{"".join(bars)}</svg>'


def _svg_line_chart(rows: list[dict[str, float | str]], color: str) -> str:
    width = 620
    height = 220
    if not rows:
        return '<div class="chart-empty">No data available.</div>'
    numeric_rows = sorted(rows, key=lambda row: float(row["strike"]))
    x_min = min(float(row["strike"]) for row in numeric_rows)
    x_max = max(float(row["strike"]) for row in numeric_rows)
    y_min = min(float(row["value"]) for row in numeric_rows)
    y_max = max(float(row["value"]) for row in numeric_rows)
    x_span = max(x_max - x_min, 1.0)
    y_span = max(y_max - y_min, 0.01)
    points = []
    markers = []
    for row in numeric_rows:
        x = 24 + ((float(row["strike"]) - x_min) / x_span) * 560
        y = 170 - ((float(row["value"]) - y_min) / y_span) * 130
        points.append(f"{x:.1f},{y:.1f}")
        markers.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{color}" />')
        markers.append(f'<text x="{x:.1f}" y="194" text-anchor="middle" class="axis">{float(row["strike"]):.0f}</text>')
    polyline = f'<polyline fill="none" stroke="{color}" stroke-width="4" points="{" ".join(points)}" />'
    return f'<svg viewBox="0 0 {width} {height}" class="chart-svg">{polyline}{"".join(markers)}</svg>'


def _svg_categorical_line_chart(rows: list[dict[str, float | str]], color: str) -> str:
    width = 620
    height = 220
    if not rows:
        return '<div class="chart-empty">No data available.</div>'
    values = [float(row["value"]) for row in rows]
    y_min = min(values)
    y_max = max(values)
    y_span = max(y_max - y_min, 0.01)
    step = 560 / max(len(rows) - 1, 1)
    points = []
    markers = []
    for index, row in enumerate(rows):
        x = 30 + index * step
        y = 170 - ((float(row["value"]) - y_min) / y_span) * 130
        points.append(f"{x:.1f},{y:.1f}")
        markers.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{color}" />')
        markers.append(f'<text x="{x:.1f}" y="194" text-anchor="middle" class="axis">{_escape(row["label"])}</text>')
    polyline = f'<polyline fill="none" stroke="{color}" stroke-width="4" points="{" ".join(points)}" />'
    return f'<svg viewBox="0 0 {width} {height}" class="chart-svg">{polyline}{"".join(markers)}</svg>'


def _svg_multi_line_chart(series: list[dict[str, Any]]) -> str:
    width = 620
    height = 220
    if not series:
        return '<div class="chart-empty">No data available.</div>'
    palette = ("#6f35ff", "#ff7b1a", "#171315", "#0f9d58", "#d93025")
    all_values = [
        float(point["value"])
        for path in series
        for point in path.get("rows", [])
        if isinstance(point, dict) and point.get("value") is not None
    ]
    if not all_values:
        return '<div class="chart-empty">No data available.</div>'
    y_min = min(all_values)
    y_max = max(all_values)
    y_span = max(y_max - y_min, 0.01)
    max_points = max(len(path.get("rows", [])) for path in series) or 1
    step = 560 / max(max_points - 1, 1)
    labels = []
    lines = []
    legend = []
    for series_index, path in enumerate(series):
        color = palette[series_index % len(palette)]
        rows = path.get("rows", [])
        points = []
        for point_index, point in enumerate(rows):
            x = 30 + point_index * step
            y = 170 - ((float(point["value"]) - y_min) / y_span) * 130
            points.append(f"{x:.1f},{y:.1f}")
            if series_index == 0:
                labels.append(
                    f'<text x="{x:.1f}" y="194" text-anchor="middle" class="axis">{_escape(point["label"])}</text>'
                )
        lines.append(
            f'<polyline fill="none" stroke="{color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" points="{" ".join(points)}" />'
        )
        legend.append(
            f'<span class="legend-item"><span class="legend-swatch" style="background:{color}"></span>{_escape(path.get("label", f"Path {series_index + 1}"))}</span>'
        )
    return (
        f'<div class="chart-with-legend"><svg viewBox="0 0 {width} {height}" class="chart-svg">{"".join(lines)}{"".join(labels)}</svg>'
        f'<div class="legend">{"".join(legend)}</div></div>'
    )


def _tab_script() -> str:
    return """
<script>
(() => {
  const buttons = Array.from(document.querySelectorAll("[data-tab-target]"));
  const panels = Array.from(document.querySelectorAll("[data-tab-panel]"));
  if (!buttons.length || !panels.length) {
    return;
  }
  const activate = (targetId) => {
    buttons.forEach((button) => {
      const active = button.dataset.tabTarget === targetId;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-selected", active ? "true" : "false");
      button.setAttribute("tabindex", active ? "0" : "-1");
    });
    panels.forEach((panel) => {
      panel.classList.toggle("is-active", panel.id === targetId);
    });
  };
  buttons.forEach((button) => {
    button.addEventListener("click", () => activate(button.dataset.tabTarget));
  });
  activate(buttons[0].dataset.tabTarget);
})();
</script>
"""


def _packet_stylesheet() -> str:
    return """
<style>
:root {
  --bg: #f5f0e7;
  --ink: #171315;
  --muted: #5e5651;
  --line: #171315;
  --panel: #fff8ef;
  --panel-2: #f3ecff;
  --accent: #6f35ff;
  --accent-2: #ff7b1a;
  --accent-3: #cbff43;
}
@page { size: A4; margin: 12mm; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); font-family: "Aptos", "Segoe UI", sans-serif; }
.packet-shell { max-width: 1360px; margin: 0 auto; padding: 18px; }
.page { page-break-after: always; padding: 20px; }
.page:last-child { page-break-after: auto; }
.hero, .panel { background: var(--panel); border: 3px solid var(--line); box-shadow: 10px 10px 0 rgba(23,19,21,.14); }
.hero { padding: 24px; }
.kicker { display: inline-block; background: var(--accent-3); border: 2px solid var(--line); font-size: 12px; font-weight: 800; letter-spacing: .12em; padding: 6px 10px; text-transform: uppercase; }
h1, h2, h3 { font-family: "Poppins", "Aptos Narrow", sans-serif; margin: 0; }
h1 { font-size: 56px; line-height: .92; margin-top: 14px; text-transform: uppercase; }
h2 { font-size: 34px; text-transform: uppercase; }
h3 { font-size: 16px; text-transform: uppercase; letter-spacing: .05em; }
p, li, td, th { font-size: 14px; line-height: 1.45; }
.muted { color: var(--muted); }
.grid { display: grid; gap: 16px; }
.grid-2 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.grid-3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.panel { padding: 18px; }
.meta { display: grid; gap: 14px; grid-template-columns: repeat(4, minmax(0, 1fr)); margin-top: 20px; }
.stat { background: var(--panel-2); border: 2px solid var(--line); padding: 12px; }
.stat-label { color: var(--muted); display: block; font-size: 11px; font-weight: 800; letter-spacing: .09em; text-transform: uppercase; }
.stat-value { display: block; font-size: 24px; font-weight: 800; margin-top: 8px; }
table { border-collapse: collapse; width: 100%; margin-top: 12px; }
th, td { border: 2px solid var(--line); padding: 10px; text-align: left; vertical-align: top; }
th { background: rgba(111,53,255,.08); }
ul { margin: 12px 0 0; padding-left: 18px; }
.chart-svg { width: 100%; height: auto; background: white; border: 2px solid var(--line); margin-top: 12px; }
.axis { fill: var(--muted); font-size: 10px; font-family: "Aptos", "Segoe UI", sans-serif; }
.tear-grid { display: grid; gap: 16px; grid-template-columns: 1.2fr 1fr; margin-top: 16px; }
.stack { display: grid; gap: 16px; }
.tabs { display: flex; flex-wrap: wrap; gap: 10px; margin: 0 auto 18px; padding: 14px; position: sticky; top: 0; z-index: 10; background: rgba(245,240,231,.92); backdrop-filter: blur(8px); }
.tab-button { appearance: none; border: 2px solid var(--line); background: white; color: var(--ink); cursor: pointer; font: inherit; font-weight: 700; padding: 10px 14px; text-transform: uppercase; letter-spacing: .04em; }
.tab-button.is-active { background: var(--accent); color: white; box-shadow: 6px 6px 0 rgba(23,19,21,.14); }
.tab-panel { display: none; }
.tab-panel.is-active { display: block; }
.overview-grid, .agent-review-grid { display: grid; gap: 16px; margin-top: 16px; }
.overview-grid { grid-template-columns: 1.1fr .9fr; }
.agent-review-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.warning-list { margin-top: 16px; }
.legend { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 10px; }
.legend-item { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 700; }
.legend-swatch { display: inline-block; width: 14px; height: 14px; border: 2px solid var(--line); }
.chart-empty { border: 2px dashed var(--line); padding: 24px; margin-top: 12px; background: white; }
@media screen {
  .page { margin-bottom: 20px; }
}
@media print {
  .packet-shell { padding: 0; }
  .tabs { display: none; }
  .tab-panel { display: block !important; }
}
@media (max-width: 900px) {
  .meta, .grid-2, .grid-3, .tear-grid, .overview-grid, .agent-review-grid { grid-template-columns: 1fr; }
  .packet-shell { padding: 12px; }
}
</style>
"""


def render_weekly_options_packet_html(packet: WeeklyOptionsPacket) -> str:
    weekly_rows = shortlist_rows(packet.weekly_result)
    tab_specs = [("overview", "Overview"), ("top-10", "Top 10")]
    if packet.agent_review is not None:
        tab_specs.append(("agent-review", "Agent Review"))
    tab_specs.extend((f"rank-{tearsheet.rank}", f"Rank {tearsheet.rank}") for tearsheet in packet.tearsheets)
    tab_buttons = "".join(
        f'<button type="button" class="tab-button" data-tab-target="{tab_id}" role="tab" aria-selected="false">{_escape(label)}</button>'
        for tab_id, label in tab_specs
    )
    panels = [
        _render_overview_panel(packet),
        _render_top_10_panel(packet, weekly_rows),
    ]
    if packet.agent_review is not None:
        panels.append(_render_agent_review_panel(packet.agent_review))
    panels.extend(
        _render_tearsheet_panel(tearsheet, packet.weekly_result.ranked_options[tearsheet.rank - 1])
        for tearsheet in packet.tearsheets
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"{_packet_stylesheet()}</head><body><div class='packet-shell'><nav class='tabs' role='tablist'>{tab_buttons}</nav>"
        f"{''.join(panels)}</div>{_tab_script()}</body></html>"
    )


def _render_overview_panel(packet: WeeklyOptionsPacket) -> str:
    clean_candidates = [option for option in packet.weekly_result.ranked_options if getattr(option, "event_risk", "unknown") == "low"]
    flagged_candidates = [option for option in packet.weekly_result.ranked_options if getattr(option, "event_risk", "unknown") != "low"]
    clean_list = "".join(
        f"<li>{_escape(option.symbol)} {_escape(option.side)} {_escape(option.expiry)} | {_escape(option.valuation_view)} | review {option.review_status}</li>"
        for option in clean_candidates[:5]
    ) or "<li>No clean swing candidates were identified in this packet.</li>"
    flagged_list = "".join(
        f"<li>{_escape(option.symbol)} {_escape(option.side)} {_escape(option.expiry)} | event {getattr(option, 'event_risk', 'unknown')} | {_escape(getattr(option, 'event_risk_detail', ''))}</li>"
        for option in flagged_candidates[:5]
    ) or "<li>No flagged event-risk candidates were identified in this packet.</li>"
    warning_markup = ""
    if packet.warnings:
        warning_markup = (
            '<div class="panel warning-list"><span class="kicker">Warnings</span><h3>Agent Review Notes</h3>'
            f"<ul>{''.join(f'<li>{_escape(item)}</li>' for item in packet.warnings)}</ul></div>"
        )
    reviewer_panel = ""
    if packet.weekly_result.review_summary:
        reviewer_panel = (
            '<div class="panel"><span class="kicker">Reviewer</span><h3>Deterministic Review Summary</h3>'
            f"<p>{_escape(packet.weekly_result.review_summary)}</p></div>"
        )
    return f"""
    <section class="page tab-panel" id="overview" data-tab-panel>
      <div class="hero">
        <span class="kicker">Quant Researcher Desk</span>
        <h2>Executive Overview</h2>
        <h1>{_escape(packet.title)}</h1>
        <p>{_escape(packet.executive_summary)}</p>
        <div class="meta">
          <div class="stat"><span class="stat-label">Generated At</span><span class="stat-value">{_escape(packet.generated_at.strftime('%Y-%m-%d %H:%M:%S %Z').strip())}</span></div>
          <div class="stat"><span class="stat-label">Shortlist</span><span class="stat-value">{len(packet.weekly_result.ranked_options)}</span></div>
          <div class="stat"><span class="stat-label">Skipped</span><span class="stat-value">{len(packet.weekly_result.skipped_underlyings)}</span></div>
          <div class="stat"><span class="stat-label">Target</span><span class="stat-value">{packet.weekly_result.request.top_n}</span></div>
        </div>
      </div>
      <div class="overview-grid">
        <div class="panel">
          <span class="kicker">Method</span>
          <h2>How To Read This Packet</h2>
          <p>{_escape(packet.methodology_summary)}</p>
          <ul>
            <li>Negative fair value gap means the option looks rich versus the model.</li>
            <li>Composite score is a review-priority score, not a buy score.</li>
            <li>Each rank tab keeps the same visual slots so weekly review stays comparable.</li>
          </ul>
        </div>
        {reviewer_panel or '<div class="panel"><span class="kicker">Scope</span><h3>Review Sequence</h3><p>Use Overview for packet context, Top 10 for shortlist comparison, Agent Review for portfolio-level synthesis, then inspect each ranked contract tab in detail.</p></div>'}
      </div>
      <div class="overview-grid">
        <div class="panel">
          <span class="kicker">Clean Swing</span>
          <h3>Cleaner Resale Candidates</h3>
          <ul>{clean_list}</ul>
        </div>
        <div class="panel">
          <span class="kicker">Event Risk</span>
          <h3>Flagged Candidates</h3>
          <ul>{flagged_list}</ul>
        </div>
      </div>
      {warning_markup}
    </section>
    """


def _render_top_10_panel(packet: WeeklyOptionsPacket, weekly_rows: list[dict[str, Any]]) -> str:
    header = (
        "<tr><th>Rank</th><th>Symbol</th><th>Contract</th><th>Side</th><th>Expiry</th><th>Strike</th><th>Premium</th>"
        "<th>Trend Regime</th><th>Stock Direction</th><th>Fair Value Gap %</th><th>Valuation View</th><th>Review Status</th></tr>"
    )
    body_rows = []
    for tearsheet, row in zip(packet.tearsheets, weekly_rows):
        body_rows.append(
            "<tr>"
            f"<td>{tearsheet.rank}</td>"
            f"<td>{_escape(row['symbol'])}</td>"
            f"<td>{_escape(tearsheet.report.contract.code)}</td>"
            f"<td>{_escape(row['side'])}</td>"
            f"<td>{_escape(row['expiry'])}</td>"
            f"<td>{_escape(row['strike'])}</td>"
            f"<td>{_escape(row['premium'])}</td>"
            f"<td>{_escape(row['trend_regime'])}</td>"
            f"<td>{_escape(row['stock_direction'])}</td>"
            f"<td>{_escape(row['fair_value_gap_pct'])}</td>"
            f"<td>{_escape(row['valuation_view'])}</td>"
            f"<td>{_escape(row['review_status'])}</td>"
            "</tr>"
        )
    return f"""
    <section class="page tab-panel" id="top-10" data-tab-panel>
      <div class="panel">
        <span class="kicker">Top 10</span>
        <h2>Top 10 Weekly Shortlist</h2>
        <table>
          <thead>{header}</thead>
          <tbody>{''.join(body_rows)}</tbody>
        </table>
      </div>
    </section>
    """


def _render_agent_review_panel(review: WeeklyAgentReviewResult) -> str:
    warning_panel = ""
    if review.warnings:
        warning_panel = (
            '<div class="panel"><span class="kicker">Warnings</span><h3>Fallback Notes</h3>'
            f"<ul>{''.join(f'<li>{_escape(item)}</li>' for item in review.warnings)}</ul></div>"
        )
    top_candidate_table = "".join(
        f"<tr><th>{_escape(label)}</th><td>{_escape(review.top_candidate.get(key, ''))}</td></tr>"
        for key, label in (
            ("rank", "Rank"),
            ("symbol", "Symbol"),
            ("option_code", "Option Code"),
            ("reason", "Reason"),
        )
    )
    return f"""
    <section class="page tab-panel" id="agent-review" data-tab-panel>
      <div class="hero">
        <span class="kicker">Agent Review</span>
        <h2>Portfolio-Level Synthesis</h2>
        <p>Model: {_escape(review.model_used)}{" (fallback)" if review.fallback_used else ""}</p>
      </div>
      <div class="agent-review-grid">
        <div class="panel"><h3>Synthesis</h3><p>{_escape(review.synthesis)}</p></div>
        <div class="panel"><h3>Reflection</h3><p>{_escape(review.reflection)}</p></div>
        <div class="panel"><h3>Deliberation</h3><p>{_escape(review.deliberation)}</p></div>
        <div class="panel"><h3>Proposed Trading Idea</h3><p>{_escape(review.proposed_trading_idea)}</p></div>
        <div class="panel"><h3>Top Candidate</h3><table>{top_candidate_table}</table></div>
        <div class="panel"><h3>Watchouts</h3><ul>{''.join(f'<li>{_escape(item)}</li>' for item in review.watchouts)}</ul></div>
        <div class="panel"><h3>Risk Controls</h3><ul>{''.join(f'<li>{_escape(item)}</li>' for item in review.risk_controls)}</ul></div>
        <div class="panel"><h3>Follow-Up Checks</h3><ul>{''.join(f'<li>{_escape(item)}</li>' for item in review.follow_up_checks)}</ul></div>
        {warning_panel}
      </div>
    </section>
    """


def _render_tearsheet_panel(tearsheet: WeeklyOptionsTearSheet, option: Any) -> str:
    report = tearsheet.report
    copy = tearsheet.writer_copy
    snapshot_rows = [
        ("Contract", report.contract.code),
        ("Type", report.contract.option_type),
        ("Strike", f"{report.contract.strike:.2f}"),
        ("Premium", f"{report.contract.market_price:.2f}"),
        ("Underlying", f"{report.underlying_price:.2f}"),
        ("Fair Value Gap", f"{report.fair_value_gap_pct:.1%}"),
        ("Valuation View", report.valuation_view),
        ("Event Risk", getattr(option, "event_risk", "unknown")),
        ("IV/HV", f"{report.implied_volatility_used:.1%} / {report.historical_volatility:.1%}"),
        ("Verdict", report.verdict),
    ]
    snapshot_table = "".join(f"<tr><th>{_escape(label)}</th><td>{_escape(value)}</td></tr>" for label, value in snapshot_rows)
    stock_context_rows = [
        ("Trend Regime", getattr(option, "trend_regime", "")),
        ("Stock Direction", getattr(option, "stock_direction", "")),
        ("Thesis Summary", getattr(option, "stock_review_summary", "")),
        ("Invalidation", getattr(option, "invalidation", "")),
        ("Catalyst View", getattr(option, "catalyst_view", "")),
        ("Alignment Status", getattr(option, "alignment_status", "")),
    ]
    stock_context_table = "".join(f"<tr><th>{_escape(label)}</th><td>{_escape(value)}</td></tr>" for label, value in stock_context_rows)
    scenario_rows = [{"label": f"{row.price_shock_pct:.0%}", "value": row.profit_loss} for row in report.scenario_rows if abs(row.iv_shift_pct) < 0.0001]
    return f"""
    <section class="page tab-panel" id="rank-{tearsheet.rank}" data-tab-panel>
      <div class="hero">
        <span class="kicker">Tear Sheet</span>
        <h2>Rank {tearsheet.rank}: {_escape(report.symbol)} {_escape(report.contract.option_type)} {report.contract.strike:.0f}</h2>
        <p>{_escape(copy.contract_takeaway)}</p>
      </div>
      <div class="tear-grid">
        <div class="stack">
          <div class="panel">
            <h3>Stock Context</h3>
            <table>{stock_context_table}</table>
          </div>
          <div class="panel">
            <h3>Contract Snapshot</h3>
            <table>{snapshot_table}</table>
          </div>
          <div class="panel">
            <h3>Black-Scholes Value Curve</h3>
            {_svg_categorical_line_chart(report.black_scholes_curve, "#6f35ff")}
          </div>
          <div class="panel">
            <h3>Monte Carlo Sample Paths</h3>
            {_svg_multi_line_chart(report.monte_carlo_paths)}
          </div>
          <div class="panel">
            <h3>Scenario Shape</h3>
            {_svg_bar_chart(scenario_rows, "#6f35ff")}
          </div>
        </div>
        <div class="stack">
          <div class="panel">
            <h3>Monte Carlo Distribution</h3>
            {_svg_bar_chart(report.monte_carlo_distribution, "#ff7b1a")}
          </div>
          <div class="panel">
            <h3>Smile Curve</h3>
            {_svg_line_chart(report.smile_curve, "#171315")}
          </div>
          <div class="panel">
            <h3>Analysis</h3>
            <p>{_escape(copy.executive_summary)}</p>
            <p>{_escape(report.resale_thesis_summary)}</p>
            <p>{_escape(report.exit_quality_summary)}</p>
            <p>{_escape(report.event_risk_summary)}</p>
            <ul>{"".join(f"<li>{_escape(item)}</li>" for item in copy.risk_callouts)}</ul>
          </div>
          <div class="panel">
            <h3>Highlighted Decisions / Action Items</h3>
            <ul>{"".join(f"<li>{_escape(item)}</li>" for item in copy.action_items)}</ul>
            <h3 style="margin-top:14px;">Questions To Verify</h3>
            <ul>{"".join(f"<li>{_escape(item)}</li>" for item in copy.questions_to_verify)}</ul>
          </div>
        </div>
      </div>
    </section>
    """


def write_weekly_options_packet_html(path: pathlib.Path, packet: WeeklyOptionsPacket) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_weekly_options_packet_html(packet), encoding="utf-8")
    return path


def _native_packet_sections(packet: WeeklyOptionsPacket) -> list[dict[str, object]]:
    sections: list[dict[str, object]] = [
        {
            "title": "Overview",
            "summary": packet.executive_summary,
            "items": [
                packet.methodology_summary,
                "Negative fair value gap means the option looks rich versus the model.",
                "Composite score is a review-priority score, not a buy score.",
                "Clean swing candidates are the lowest event-risk contracts in the current resale lane.",
                "Flagged event-risk candidates stay visible, but they carry an explicit ranking penalty and review caution.",
            ]
            + [f"Warning: {warning}" for warning in packet.warnings],
            "table": [
                {
                    "generated_at": packet.generated_at.strftime("%Y-%m-%d %H:%M:%S %Z").strip(),
                    "shortlist": len(packet.weekly_result.ranked_options),
                    "skipped": len(packet.weekly_result.skipped_underlyings),
                    "target": packet.weekly_result.request.top_n,
                }
            ],
        },
        {
            "title": "Top 10 Weekly Shortlist",
            "table": [
                {
                    "rank": tearsheet.rank,
                    "symbol": tearsheet.report.symbol,
                    "contract": tearsheet.report.contract.code,
                    "side": tearsheet.report.contract.option_type,
                    "expiry": tearsheet.report.contract.expiry,
                    "strike": f"{tearsheet.report.contract.strike:.2f}",
                    "premium": f"{tearsheet.report.contract.market_price:.2f}",
                    "trend_regime": packet.weekly_result.ranked_options[tearsheet.rank - 1].trend_regime,
                    "stock_direction": packet.weekly_result.ranked_options[tearsheet.rank - 1].stock_direction,
                    "fair_value_gap_pct": f"{tearsheet.report.fair_value_gap_pct:.1%}",
                    "valuation_view": tearsheet.report.valuation_view,
                    "review_status": packet.weekly_result.ranked_options[tearsheet.rank - 1].review_status,
                    "event_risk": getattr(packet.weekly_result.ranked_options[tearsheet.rank - 1], "event_risk", "unknown"),
                }
                for tearsheet in packet.tearsheets
            ],
        },
    ]
    if packet.agent_review is not None:
        sections.append(
            {
                "title": "Agent Review",
                "summary": packet.agent_review.synthesis,
                "items": [
                    f"Reflection: {packet.agent_review.reflection}",
                    f"Deliberation: {packet.agent_review.deliberation}",
                    f"Proposed idea: {packet.agent_review.proposed_trading_idea}",
                    f"Top candidate: {packet.agent_review.top_candidate.get('rank', '')} {packet.agent_review.top_candidate.get('symbol', '')} {packet.agent_review.top_candidate.get('option_code', '')}",
                ]
                + [f"Watchout: {item}" for item in packet.agent_review.watchouts]
                + [f"Risk control: {item}" for item in packet.agent_review.risk_controls]
                + [f"Follow-up: {item}" for item in packet.agent_review.follow_up_checks]
                + [f"Warning: {item}" for item in packet.agent_review.warnings],
            }
        )
    sections.append(
        {
            "title": "Candidate Buckets",
            "table": [
                {
                    "bucket": "clean_swing_candidate",
                    "symbols": ", ".join(
                        option.symbol for option in packet.weekly_result.ranked_options if getattr(option, "event_risk", "unknown") == "low"
                    ) or "none",
                },
                {
                    "bucket": "flagged_event_candidate",
                    "symbols": ", ".join(
                        option.symbol for option in packet.weekly_result.ranked_options if getattr(option, "event_risk", "unknown") != "low"
                    ) or "none",
                },
            ],
        }
    )
    for tearsheet in packet.tearsheets:
        report = tearsheet.report
        copy = tearsheet.writer_copy
        sections.extend(
            [
                {
                    "title": f"Tear Sheet {tearsheet.rank}: {report.contract.code}",
                    "summary": copy.contract_takeaway,
                    "table": [
                        {
                            "symbol": report.symbol,
                            "contract": report.contract.code,
                            "trend_regime": packet.weekly_result.ranked_options[tearsheet.rank - 1].trend_regime,
                            "stock_direction": packet.weekly_result.ranked_options[tearsheet.rank - 1].stock_direction,
                            "strike": f"{report.contract.strike:.2f}",
                            "premium": f"{report.contract.market_price:.2f}",
                            "fair_value_gap_pct": f"{report.fair_value_gap_pct:.1%}",
                            "valuation_view": report.valuation_view,
                            "verdict": report.verdict,
                            "event_risk": getattr(packet.weekly_result.ranked_options[tearsheet.rank - 1], "event_risk", "unknown"),
                        }
                    ],
                },
                {
                    "title": "Stock Context",
                    "table": [
                        {
                            "trend_regime": packet.weekly_result.ranked_options[tearsheet.rank - 1].trend_regime,
                            "stock_direction": packet.weekly_result.ranked_options[tearsheet.rank - 1].stock_direction,
                            "thesis_summary": packet.weekly_result.ranked_options[tearsheet.rank - 1].stock_review_summary,
                            "invalidation": packet.weekly_result.ranked_options[tearsheet.rank - 1].invalidation,
                            "catalyst_view": packet.weekly_result.ranked_options[tearsheet.rank - 1].catalyst_view,
                        }
                    ],
                },
                {
                    "title": "Black-Scholes Value Curve",
                    "table": report.black_scholes_curve,
                },
                {
                    "title": "Monte Carlo Sample Paths",
                    "table": [
                        {
                            "path": str(series.get("label", "")),
                            "values": ", ".join(
                                f"{point.get('label')}: {point.get('value')}"
                                for point in series.get("rows", [])
                            ),
                        }
                        for series in report.monte_carlo_paths
                    ],
                },
                {
                    "title": "Scenario Shape",
                    "table": [
                        {
                            "price_shock_pct": f"{row.price_shock_pct:.0%}",
                            "underlying_price": f"{row.underlying_price:.2f}",
                            "option_value": f"{row.option_value:.2f}",
                            "profit_loss": f"{row.profit_loss:.2f}",
                        }
                        for row in report.scenario_rows
                        if abs(row.iv_shift_pct) < 0.0001
                    ],
                },
                {
                    "title": "Monte Carlo Distribution",
                    "chart": {"rows": report.monte_carlo_distribution},
                },
                {
                    "title": "Smile Curve",
                    "table": report.smile_curve,
                },
                {
                    "title": "Highlighted Decisions / Action Items",
                    "summary": copy.executive_summary,
                    "items": [
                        report.resale_thesis_summary,
                        report.exit_quality_summary,
                        report.event_risk_summary,
                    ]
                    + copy.action_items
                    + copy.questions_to_verify
                    + copy.risk_callouts,
                },
            ]
        )
    return sections


def write_weekly_options_packet_pdf(path: pathlib.Path, packet: WeeklyOptionsPacket) -> pathlib.Path:
    html_path = write_weekly_options_packet_html(path.with_suffix(".html"), packet)
    try:
        return render_html_file_to_pdf_with_chrome(html_path, path)
    except ReportRenderError:
        return write_native_pdf_report(
            packet.title,
            _native_packet_sections(packet),
            {
                "generated_at": packet.generated_at.strftime("%Y-%m-%d %H:%M:%S %Z").strip(),
                "shortlist": len(packet.weekly_result.ranked_options),
            },
            path,
        )
