"""Institutional HTML and PDF report rendering helpers."""

from __future__ import annotations

import html
import pathlib
import re
from collections.abc import Mapping, Sequence
from typing import Any


class ReportRenderError(Exception):
    """Raised when a requested report format cannot be rendered."""


def _escape(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _slug_label(value: Any) -> str:
    return str(value).replace("_", " ").strip().title()


def _pdf_safe(value: object) -> str:
    text = re.sub(r"<[^>]+>", "", str(value))
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _pdf_escape(value: object) -> str:
    return _pdf_safe(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _wrap_text(value: object, max_chars: int) -> list[str]:
    words = _pdf_safe(value).replace("\n", " \n ").split()
    lines: list[str] = []
    current = ""
    for word in words:
        if word == "\n":
            if current:
                lines.append(current)
                current = ""
            continue
        candidate = word if not current else f"{current} {word}"
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


def _render_metadata(metadata: Mapping[str, Any]) -> str:
    if not metadata:
        return ""
    cards = "\n".join(
        (
            '<div class="meta-card">'
            f'<span class="meta-label">{_escape(_slug_label(key))}</span>'
            f'<strong>{_escape(value)}</strong>'
            "</div>"
        )
        for key, value in metadata.items()
    )
    return f'<section class="metadata-grid" aria-label="Report metadata">{cards}</section>'


def _normalise_rows(table: Any) -> tuple[list[str], list[list[Any]]]:
    if isinstance(table, Mapping):
        columns = [str(column) for column in table.get("columns", [])]
        raw_rows = table.get("rows", [])
    else:
        columns = []
        raw_rows = table

    rows = list(raw_rows or [])
    if not columns and rows and isinstance(rows[0], Mapping):
        columns = [str(column) for column in rows[0].keys()]
    if not columns and rows and isinstance(rows[0], Sequence) and not isinstance(rows[0], (str, bytes)):
        columns = [f"Column {index}" for index in range(1, len(rows[0]) + 1)]

    normalised_rows: list[list[Any]] = []
    for row in rows:
        if isinstance(row, Mapping):
            normalised_rows.append([row.get(column, "") for column in columns])
        elif isinstance(row, Sequence) and not isinstance(row, (str, bytes)):
            normalised_rows.append(list(row))
        else:
            normalised_rows.append([row])
    return columns, normalised_rows


def _render_table(table: Any) -> str:
    columns, rows = _normalise_rows(table)
    if not rows:
        return '<p class="muted">No rows available.</p>'
    head = "".join(f"<th>{_escape(_slug_label(column))}</th>" for column in columns)
    body_rows = []
    for row in rows:
        cells = "".join(f"<td>{_escape(value)}</td>" for value in row)
        body_rows.append(f"<tr>{cells}</tr>")
    return (
        '<div class="table-wrap"><table>'
        f"<thead><tr>{head}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        "</table></div>"
    )


def _normalise_chart_rows(chart: Any) -> list[dict[str, float | str]]:
    rows = chart.get("rows", []) if isinstance(chart, Mapping) else chart
    normalized: list[dict[str, float | str]] = []
    for row in rows or []:
        if isinstance(row, Mapping):
            label = str(row.get("label", ""))
            value = row.get("value", 0)
        elif isinstance(row, Sequence) and not isinstance(row, (str, bytes)) and len(row) >= 2:
            label = str(row[0])
            value = row[1]
        else:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = 0.0
        normalized.append({"label": label, "value": number})
    return normalized


def _render_chart(chart: Any) -> str:
    rows = _normalise_chart_rows(chart)
    if not rows:
        return '<p class="muted">No chart data available.</p>'
    max_abs = max(abs(float(row["value"])) for row in rows) or 1.0
    rendered_rows = []
    for row in rows:
        value = float(row["value"])
        width = max(abs(value) / max_abs * 100, 2)
        tone = "positive" if value >= 0 else "negative"
        rendered_rows.append(
            '<div class="chart-row">'
            f'<div class="chart-label">{_escape(row["label"])}</div>'
            '<div class="chart-track">'
            f'<div class="chart-bar {tone}" style="width:{width:.1f}%"></div>'
            "</div>"
            f'<div class="chart-value">{_escape(f"{value:.2f}")}</div>'
            "</div>"
        )
    return f'<div class="bar-chart">{"".join(rendered_rows)}</div>'


def _render_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        paragraphs = [part.strip() for part in content.split("\n\n") if part.strip()]
        return "\n".join(f"<p>{_escape(paragraph).replace(chr(10), '<br>')}</p>" for paragraph in paragraphs)
    if isinstance(content, Mapping):
        if "table" in content:
            return _render_table(content["table"])
        if "chart" in content:
            return _render_chart(content["chart"])
        return _render_table([content])
    if isinstance(content, Sequence) and not isinstance(content, (str, bytes)):
        items = list(content)
        if items and all(isinstance(item, Mapping) for item in items):
            return _render_table(items)
        rendered_items = "".join(f"<li>{_escape(item)}</li>" for item in items)
        return f"<ul>{rendered_items}</ul>"
    return f"<p>{_escape(content)}</p>"


def _render_section(section: Any, index: int) -> str:
    if isinstance(section, Mapping):
        heading = section.get("title") or section.get("heading") or f"Section {index}"
        kicker = section.get("kicker") or f"{index:02d}"
        content_parts = [
            _render_content(section.get("summary")),
            _render_content(section.get("content") or section.get("body")),
            _render_content(section.get("items")),
            _render_table(section["table"]) if "table" in section else "",
            _render_chart(section["chart"]) if "chart" in section else "",
        ]
    else:
        heading = f"Section {index}"
        kicker = f"{index:02d}"
        content_parts = [_render_content(section)]
    body = "\n".join(part for part in content_parts if part)
    return (
        '<article class="report-section">'
        '<div class="section-kicker">'
        f"<span>{_escape(kicker)}</span>"
        "</div>"
        f"<h2>{_escape(heading)}</h2>"
        f"{body}"
        "</article>"
    )


class _NativePdfCanvas:
    width = 595
    height = 842
    margin = 42

    def __init__(self) -> None:
        self.pages: list[list[str]] = []
        self.commands: list[str] = []
        self.y = self.height - self.margin
        self.new_page()

    def new_page(self) -> None:
        if getattr(self, "commands", None):
            self.pages.append(self.commands)
        self.commands = []
        self.y = self.height - self.margin
        self.rect(0, 0, self.width, self.height, (0.098, 0.078, 0.078))

    def ensure(self, height: float) -> None:
        if self.y - height < self.margin:
            self.new_page()

    def color(self, rgb: tuple[float, float, float]) -> str:
        return f"{rgb[0]:.3f} {rgb[1]:.3f} {rgb[2]:.3f}"

    def rect(self, x: float, y: float, width: float, height: float, rgb: tuple[float, float, float]) -> None:
        self.commands.append(f"{self.color(rgb)} rg {x:.2f} {y:.2f} {width:.2f} {height:.2f} re f")

    def text(self, x: float, y: float, text: object, size: int = 10, rgb: tuple[float, float, float] = (0.969, 0.957, 0.949), font: str = "F1") -> None:
        self.commands.append(f"BT /{font} {size} Tf {self.color(rgb)} rg {x:.2f} {y:.2f} Td ({_pdf_escape(text)}) Tj ET")

    def paragraph(self, text: object, size: int = 10, max_chars: int = 88, leading: int = 14) -> None:
        lines = _wrap_text(text, max_chars)
        self.ensure(len(lines) * leading + 8)
        for line in lines:
            self.text(self.margin, self.y, line, size=size)
            self.y -= leading
        self.y -= 6

    def heading(self, text: object) -> None:
        self.ensure(44)
        self.text(self.margin, self.y, text, size=18, rgb=(1.0, 0.275, 0.196), font="F2")
        self.y -= 26

    def table(self, rows: Any) -> None:
        columns, normalized_rows = _normalise_rows(rows)
        if not normalized_rows:
            self.paragraph("No rows available.", size=9)
            return
        col_count = max(len(columns), 1)
        col_width = (self.width - self.margin * 2) / col_count
        self.ensure(28)
        for index, column in enumerate(columns):
            self.text(self.margin + index * col_width, self.y, _slug_label(column), size=8, rgb=(0.659, 0.635, 0.620), font="F2")
        self.y -= 14
        for row in normalized_rows[:18]:
            wrapped_cells = [_wrap_text(cell, max(int(col_width / 5.4), 12)) for cell in row[:col_count]]
            row_lines = max(len(cell) for cell in wrapped_cells) if wrapped_cells else 1
            self.ensure(row_lines * 11 + 8)
            for line_index in range(row_lines):
                for col_index, cell_lines in enumerate(wrapped_cells):
                    if line_index < len(cell_lines):
                        self.text(self.margin + col_index * col_width, self.y - line_index * 11, cell_lines[line_index], size=8)
            self.y -= row_lines * 11 + 8
        self.y -= 6

    def chart(self, chart: Any) -> None:
        rows = _normalise_chart_rows(chart)
        if not rows:
            self.paragraph("No chart data available.", size=9)
            return
        max_abs = max(abs(float(row["value"])) for row in rows) or 1.0
        for row in rows:
            self.ensure(28)
            value = float(row["value"])
            self.text(self.margin, self.y, row["label"], size=9, font="F2")
            bar_width = abs(value) / max_abs * 260
            color = (1.0, 0.275, 0.196) if value >= 0 else (0.906, 0.298, 0.235)
            self.rect(self.margin + 120, self.y - 2, bar_width, 8, color)
            self.text(self.margin + 395, self.y, f"{value:.2f}", size=9, rgb=(0.659, 0.635, 0.620))
            self.y -= 22
        self.y -= 6

    def finish(self) -> list[str]:
        if self.commands:
            self.pages.append(self.commands)
            self.commands = []
        return ["\n".join(page) for page in self.pages]


def _section_title(section: Any, index: int) -> str:
    if isinstance(section, Mapping):
        return str(section.get("title") or section.get("heading") or f"Section {index}")
    return f"Section {index}"


def _write_pdf_bytes(pages: list[str], output_path: pathlib.Path) -> pathlib.Path:
    objects: list[bytes] = []

    def add_object(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    font_regular = add_object(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    font_bold = add_object(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
    page_refs: list[int] = []
    content_refs: list[int] = []
    for page in pages:
        content = page.encode("latin-1", errors="replace")
        content_refs.append(add_object(b"<< /Length " + str(len(content)).encode("ascii") + b" >>\nstream\n" + content + b"\nendstream"))
        page_refs.append(0)
    pages_ref = len(objects) + len(pages) + 1
    for index, content_ref in enumerate(content_refs):
        page_refs[index] = add_object(
            (
                f"<< /Type /Page /Parent {pages_ref} 0 R /MediaBox [0 0 595 842] "
                f"/Resources << /Font << /F1 {font_regular} 0 R /F2 {font_bold} 0 R >> >> "
                f"/Contents {content_ref} 0 R >>"
            ).encode("ascii")
        )
    kids = " ".join(f"{ref} 0 R" for ref in page_refs)
    add_object(f"<< /Type /Pages /Kids [{kids}] /Count {len(page_refs)} >>".encode("ascii"))
    catalog_ref = add_object(f"<< /Type /Catalog /Pages {pages_ref} 0 R >>".encode("ascii"))

    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode("ascii"))
        output.extend(body)
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_ref} 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(bytes(output))
    return output_path


def write_native_pdf_report(
    title: str,
    sections: Sequence[Any],
    metadata: Mapping[str, Any] | None,
    output_path: str | pathlib.Path,
) -> pathlib.Path:
    """Write a dependency-free PDF report for Telegram attachments."""

    canvas = _NativePdfCanvas()
    canvas.text(canvas.margin, canvas.y, "QUANT RESEARCHER DESK", size=10, rgb=(1.0, 0.275, 0.196), font="F2")
    canvas.y -= 30
    for line in _wrap_text(title.upper(), 30):
        canvas.text(canvas.margin, canvas.y, line, size=28, font="F2")
        canvas.y -= 32
    canvas.y -= 10
    for key, value in (metadata or {}).items():
        canvas.text(canvas.margin, canvas.y, f"{_slug_label(key)}: {value}", size=10, rgb=(0.659, 0.635, 0.620))
        canvas.y -= 14
    canvas.y -= 18

    for index, section in enumerate(sections, start=1):
        canvas.heading(_section_title(section, index))
        if isinstance(section, Mapping):
            if section.get("summary"):
                canvas.paragraph(section["summary"], size=10)
            if section.get("content") or section.get("body"):
                canvas.paragraph(section.get("content") or section.get("body"), size=10)
            if section.get("items"):
                for item in list(section["items"]):
                    canvas.paragraph(f"- {item}", size=9)
            if "chart" in section:
                canvas.chart(section["chart"])
            if "table" in section:
                canvas.table(section["table"])
        else:
            canvas.paragraph(section, size=10)
    return _write_pdf_bytes(canvas.finish(), pathlib.Path(output_path))


def _stylesheet() -> str:
    return """
:root {
  --base: #191414;
  --panel: #241f1d;
  --panel-2: #302927;
  --ink: #f7f4f2;
  --muted: #a8a29e;
  --line: #4a403c;
  --accent: #ff4632;
  --accent-soft: rgba(255, 70, 50, 0.14);
  --positive: #2ecc71;
  --risk: #e74c3c;
  --watch: #f39c12;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background:
    radial-gradient(circle at 12% 8%, rgba(255, 70, 50, 0.18), transparent 30%),
    radial-gradient(circle at 82% 0%, rgba(46, 204, 113, 0.10), transparent 24%),
    linear-gradient(135deg, #191414 0%, #211b19 52%, #0f0c0b 100%);
  color: var(--ink);
  font-family: "Inter", "Aptos", "Segoe UI", sans-serif;
  line-height: 1.55;
}
.page {
  max-width: 1080px;
  margin: 0 auto;
  padding: 48px 32px 64px;
}
.hero {
  border: 1px solid var(--line);
  border-radius: 28px;
  background: linear-gradient(145deg, rgba(48,41,39,0.96), rgba(25,20,20,0.92));
  box-shadow: 0 28px 80px rgba(0, 0, 0, 0.32);
  padding: 42px;
  position: relative;
  overflow: hidden;
}
.hero:after {
  content: "";
  position: absolute;
  inset: auto -80px -120px auto;
  width: 320px;
  height: 320px;
  border-radius: 50%;
  border: 48px solid rgba(255, 70, 50, 0.12);
}
.eyebrow {
  color: var(--accent);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.22em;
  text-transform: uppercase;
}
h1 {
  font-family: "Poppins", "Inter", sans-serif;
  font-size: clamp(42px, 7vw, 76px);
  line-height: 0.96;
  margin: 16px 0 0;
  max-width: 780px;
  text-transform: uppercase;
}
.metadata-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 14px;
  margin: 24px 0 0;
}
.meta-card {
  background: rgba(36, 31, 29, 0.78);
  border: 1px solid var(--line);
  border-radius: 18px;
  padding: 16px;
}
.meta-label {
  color: var(--muted);
  display: block;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}
.meta-card strong {
  display: block;
  font-size: 19px;
  margin-top: 6px;
}
.report-section {
  background: rgba(36, 31, 29, 0.88);
  border: 1px solid var(--line);
  border-radius: 24px;
  margin-top: 22px;
  padding: 30px;
  page-break-inside: avoid;
}
.report-section:nth-of-type(2n) {
  background: linear-gradient(145deg, rgba(48,41,39,0.92), rgba(25,20,20,0.88));
}
.section-kicker span {
  background: var(--accent-soft);
  border-radius: 999px;
  color: var(--accent);
  display: inline-block;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.14em;
  padding: 6px 10px;
}
h2 {
  font-family: "Poppins", "Inter", sans-serif;
  font-size: 30px;
  margin: 14px 0;
}
p, li { color: var(--ink); font-size: 16px; }
ul { margin: 12px 0 0; padding-left: 22px; }
.muted { color: var(--muted); }
.table-wrap { overflow-x: auto; margin-top: 16px; }
table {
  border-collapse: collapse;
  min-width: 100%;
  overflow: hidden;
}
th, td {
  border-bottom: 1px solid var(--line);
  padding: 12px 14px;
  text-align: left;
  vertical-align: top;
}
th {
  color: var(--muted);
  font-size: 11px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}
td { font-variant-numeric: tabular-nums; }
.bar-chart {
  display: grid;
  gap: 14px;
  margin-top: 18px;
}
.chart-row {
  align-items: center;
  display: grid;
  gap: 12px;
  grid-template-columns: minmax(120px, 0.8fr) minmax(180px, 2fr) 80px;
}
.chart-label {
  color: var(--ink);
  font-size: 14px;
  font-weight: 700;
}
.chart-track {
  background: rgba(255,255,255,0.08);
  border: 1px solid var(--line);
  border-radius: 999px;
  height: 16px;
  overflow: hidden;
}
.chart-bar {
  height: 100%;
}
.chart-bar.positive { background: linear-gradient(90deg, var(--accent), #ff8b78); }
.chart-bar.negative { background: linear-gradient(90deg, var(--risk), #ff9a8f); }
.chart-value {
  color: var(--muted);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 13px;
  text-align: right;
}
.tone-note {
  border-left: 3px solid var(--accent);
  color: var(--muted);
  margin-top: 18px;
  padding-left: 14px;
}
@media print {
  body { background: var(--base); }
  .page { max-width: none; padding: 0; }
  .hero, .report-section { box-shadow: none; }
}
@media (max-width: 720px) {
  .page { padding: 24px 14px 36px; }
  .hero, .report-section { border-radius: 18px; padding: 22px; }
  h1 { font-size: 36px; }
  h2 { font-size: 24px; }
  .chart-row { grid-template-columns: 1fr; gap: 6px; }
  .chart-value { text-align: left; }
  th, td { padding: 10px 8px; }
}
"""


def render_report_html(title: str, sections: Sequence[Any], metadata: Mapping[str, Any] | None = None) -> str:
    """Render a printable institutional HTML report."""

    safe_title = _escape(title)
    rendered_sections = "\n".join(_render_section(section, index) for index, section in enumerate(sections, start=1))
    rendered_metadata = _render_metadata(metadata or {})
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title}</title>
  <style>{_stylesheet()}</style>
</head>
<body>
  <main class="page">
    <header class="hero">
      <div class="eyebrow">Quant Researcher Desk</div>
      <h1>{safe_title}</h1>
      {rendered_metadata}
    </header>
    {rendered_sections}
  </main>
</body>
</html>
"""


def write_html_report(
    title: str,
    sections: Sequence[Any],
    metadata: Mapping[str, Any] | None,
    output_path: str | pathlib.Path,
) -> pathlib.Path:
    """Write a rendered HTML report and return its path."""

    path = pathlib.Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report_html(title, sections, metadata), encoding="utf-8")
    return path


def render_pdf_report(
    title: str,
    sections: Sequence[Any],
    metadata: Mapping[str, Any] | None,
    output_path: str | pathlib.Path,
    *,
    html_companion_path: str | pathlib.Path | None = None,
) -> pathlib.Path:
    """Render a PDF report with Playwright, falling back to a native PDF."""

    pdf_path = pathlib.Path(output_path)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        return write_native_pdf_report(title, sections, metadata, pdf_path)

    html_path = pathlib.Path(html_companion_path) if html_companion_path else pdf_path.with_suffix(".html")
    html_path = write_html_report(title, sections, metadata, html_path)
    html_text = html_path.read_text(encoding="utf-8")

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page()
            page.set_content(html_text, wait_until="load")
            page.pdf(
                path=str(pdf_path),
                format="A4",
                print_background=True,
                margin={"top": "18mm", "right": "14mm", "bottom": "18mm", "left": "14mm"},
            )
            browser.close()
    except (PlaywrightError, OSError) as exc:
        raise ReportRenderError(
            "PDF rendering failed; ensure Playwright and Chromium are installed. "
            f"Printable HTML companion written to {html_path}."
        ) from exc
    return pdf_path


def render_image_report(
    title: str,
    sections: Sequence[Any],
    metadata: Mapping[str, Any] | None,
    output_path: str | pathlib.Path,
    *,
    html_companion_path: str | pathlib.Path | None = None,
    viewport_width: int = 1400,
    viewport_height: int = 1800,
) -> pathlib.Path:
    """Render the report as a PNG preview suitable for Telegram."""

    image_path = pathlib.Path(output_path)
    image_path.parent.mkdir(parents=True, exist_ok=True)
    html_path = pathlib.Path(html_companion_path) if html_companion_path else image_path.with_suffix(".html")
    html_path = write_html_report(title, sections, metadata, html_path)
    html_text = html_path.read_text(encoding="utf-8")

    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        raise ReportRenderError(
            "Image rendering requires the Playwright Python package and its managed Chromium runtime. "
            f"Printable HTML companion written to {html_path}. System Chrome was not launched."
        ) from exc

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": viewport_width, "height": viewport_height})
            page.set_content(html_text, wait_until="load")
            page.screenshot(path=str(image_path), full_page=True)
            browser.close()
    except (PlaywrightError, OSError) as exc:
        raise ReportRenderError(
            "Image rendering failed; ensure Playwright/Chromium is installed. "
            f"Printable HTML companion written to {html_path}."
        ) from exc
    return image_path
