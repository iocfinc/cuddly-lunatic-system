"""Institutional HTML and PDF report rendering helpers."""

from __future__ import annotations

import html
import math
import os
import pathlib
import re
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from typing import Any


class ReportRenderError(Exception):
    """Raised when a requested report format cannot be rendered."""


REPORT_THEME = {
    "base": "#191414",
    "panel": "#241f1d",
    "panel_2": "#302927",
    "ink": "#f7f4f2",
    "muted": "#a8a29e",
    "line": "#4a403c",
    "accent": "#ff4632",
    "positive": "#2ecc71",
    "risk": "#e74c3c",
    "watch": "#f39c12",
    "heading_font": '"Poppins", "Inter", sans-serif',
    "body_font": '"Inter", "Aptos", "Segoe UI", sans-serif',
    "radius": "8px",
}


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


def _normalise_line_series(chart: Any) -> list[dict[str, Any]]:
    if isinstance(chart, Mapping) and chart.get("series"):
        raw_series = list(chart.get("series", []))
    else:
        raw_series = [{"label": chart.get("label", "Series"), "rows": chart.get("rows", [])}] if isinstance(chart, Mapping) else []
    normalized: list[dict[str, Any]] = []
    for index, series in enumerate(raw_series, start=1):
        if not isinstance(series, Mapping):
            continue
        rows = _normalise_chart_rows({"rows": series.get("rows", [])})
        if not rows:
            continue
        normalized.append(
            {
                "label": str(series.get("label", f"Series {index}")),
                "rows": rows,
            }
        )
    return normalized


def _render_line_chart(chart: Any) -> str:
    series = _normalise_line_series(chart)
    if not series:
        return '<p class="muted">No chart data available.</p>'
    width = 720
    height = 280
    left = 56
    right = 24
    top = 20
    bottom = 44
    plot_width = width - left - right
    plot_height = height - top - bottom
    max_points = max(len(current["rows"]) for current in series)
    labels = [str(row["label"]) for row in series[0]["rows"]]
    values = [float(row["value"]) for current in series for row in current["rows"]]
    min_value = min(values)
    max_value = max(values)
    if math.isclose(min_value, max_value):
        min_value -= 1.0
        max_value += 1.0
    colors = ["#6f35ff", "#ff7b1a", "#171315", "#26a69a", "#ef476f"]

    def point_at(index: int, value: float) -> tuple[float, float]:
        x = left + (plot_width * index / max(max_points - 1, 1))
        y = top + ((max_value - value) / (max_value - min_value)) * plot_height
        return x, y

    grid_lines = []
    for tick in range(5):
        value = max_value - ((max_value - min_value) * tick / 4)
        y = top + (plot_height * tick / 4)
        grid_lines.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}" class="line-chart-grid" />')
        grid_lines.append(f'<text x="{left - 8}" y="{y + 4:.1f}" text-anchor="end" class="line-chart-axis">{_escape(f"{value:.2f}")}</text>')

    x_labels = []
    for index, label in enumerate(labels):
        x, _ = point_at(index, min_value)
        x_labels.append(f'<text x="{x:.1f}" y="{height - 14}" text-anchor="middle" class="line-chart-axis">{_escape(label)}</text>')

    polylines = []
    legend = []
    for index, current in enumerate(series):
        color = colors[index % len(colors)]
        points = [point_at(row_index, float(row["value"])) for row_index, row in enumerate(current["rows"])]
        polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
        markers = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{color}" />' for x, y in points)
        polylines.append(f'<polyline points="{polyline}" fill="none" stroke="{color}" stroke-width="3" />{markers}')
        legend.append(
            '<div class="series-label">'
            f'<span class="series-swatch" style="background:{color}"></span>'
            f'<span>{_escape(current["label"])}</span>'
            "</div>"
        )

    return (
        '<div class="line-chart">'
        f'<svg viewBox="0 0 {width} {height}" class="line-chart-svg" role="img" aria-label="Line chart">'
        f'{"".join(grid_lines)}'
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height - bottom}" class="line-chart-axis-line" />'
        f'<line x1="{left}" y1="{height - bottom}" x2="{width - right}" y2="{height - bottom}" class="line-chart-axis-line" />'
        f'{"".join(polylines)}'
        f'{"".join(x_labels)}'
        "</svg>"
        f'<div class="line-chart-legend">{"".join(legend)}</div>'
        "</div>"
    )


def _render_chart(chart: Any) -> str:
    if isinstance(chart, Mapping) and str(chart.get("type", "")).lower() == "line":
        return _render_line_chart(chart)
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


def _render_relationship_map(map_data: Any) -> str:
    if not isinstance(map_data, Mapping):
        return ""
    columns = list(map_data.get("columns", []))
    edges = list(map_data.get("edges", []))
    if not columns:
        return '<p class="muted">No relationship map available.</p>'

    rendered_columns = []
    for column in columns:
        if not isinstance(column, Mapping):
            continue
        items = []
        for item in column.get("items", []) or []:
            if not isinstance(item, Mapping):
                continue
            items.append(
                '<div class="map-node">'
                f'<strong>{_escape(item.get("symbol", ""))}</strong>'
                f'<span>{_escape(item.get("name", ""))}</span>'
                f'<em>{_escape(item.get("industry", ""))}</em>'
                "</div>"
            )
        column_body = "".join(items) or '<p class="muted">No nodes in scope.</p>'
        rendered_columns.append(
            '<div class="map-column">'
            f'<h3>{_escape(column.get("label", ""))}</h3>'
            f"{column_body}"
            "</div>"
        )
    rendered_edges = "".join(
        '<li>'
        f'<code>{_escape(edge.get("source", ""))} -> {_escape(edge.get("target", ""))}</code>'
        f'<span>{_escape(edge.get("relationship", ""))}</span>'
        "</li>"
        for edge in edges
        if isinstance(edge, Mapping)
    )
    return (
        '<div class="relationship-map">'
        f'<div class="map-grid">{"".join(rendered_columns)}</div>'
        f'<ul class="map-edges">{rendered_edges or "<li><span>No direct edges in scope yet.</span></li>"}</ul>'
        "</div>"
    )


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
            _render_relationship_map(section["relationship_map"]) if "relationship_map" in section else "",
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

    def line(self, x1: float, y1: float, x2: float, y2: float, rgb: tuple[float, float, float], width: float = 1.4) -> None:
        self.commands.append(
            f"{width:.2f} w {self.color(rgb)} RG {x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S"
        )

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
        if isinstance(chart, Mapping) and str(chart.get("type", "")).lower() == "line":
            self.line_chart(chart)
            return
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

    def line_chart(self, chart: Any) -> None:
        series = _normalise_line_series(chart)
        if not series:
            self.paragraph("No chart data available.", size=9)
            return
        chart_height = 120
        chart_width = 420
        left = self.margin + 48
        bottom = self.y - chart_height
        values = [float(row["value"]) for current in series for row in current["rows"]]
        min_value = min(values)
        max_value = max(values)
        if math.isclose(min_value, max_value):
            min_value -= 1.0
            max_value += 1.0
        colors = [
            (0.435, 0.208, 1.0),
            (1.0, 0.482, 0.102),
            (0.090, 0.075, 0.075),
            (0.149, 0.651, 0.604),
            (0.937, 0.278, 0.435),
        ]
        max_points = max(len(current["rows"]) for current in series)
        self.ensure(chart_height + 48 + len(series) * 12)
        self.line(left, bottom, left, self.y, (0.659, 0.635, 0.620), width=0.8)
        self.line(left, bottom, left + chart_width, bottom, (0.659, 0.635, 0.620), width=0.8)

        def point_at(index: int, value: float) -> tuple[float, float]:
            x = left + chart_width * index / max(max_points - 1, 1)
            y = bottom + ((value - min_value) / (max_value - min_value)) * chart_height
            return x, y

        for tick in range(5):
            tick_value = min_value + (max_value - min_value) * tick / 4
            y = bottom + chart_height * tick / 4
            self.line(left, y, left + chart_width, y, (0.235, 0.216, 0.208), width=0.4)
            self.text(self.margin, y - 2, f"{tick_value:.2f}", size=7, rgb=(0.659, 0.635, 0.620))

        for series_index, current in enumerate(series):
            color = colors[series_index % len(colors)]
            points = [point_at(row_index, float(row["value"])) for row_index, row in enumerate(current["rows"])]
            for start, end in zip(points, points[1:]):
                self.line(start[0], start[1], end[0], end[1], color, width=1.3)
            self.text(left + chart_width + 10, self.y - series_index * 12, current["label"], size=7, rgb=color)
        self.y = bottom - 22

    def relationship_map(self, map_data: Any) -> None:
        if not isinstance(map_data, Mapping):
            return
        columns = list(map_data.get("columns", []))
        if not columns:
            self.paragraph("No relationship map available.", size=9)
            return
        self.ensure(42)
        col_width = (self.width - self.margin * 2 - 24) / max(len(columns), 1)
        top_y = self.y
        max_y_drop = 0
        for col_index, column in enumerate(columns):
            if not isinstance(column, Mapping):
                continue
            x = self.margin + col_index * (col_width + 12)
            self.text(x, top_y, column.get("label", ""), size=9, rgb=(1.0, 0.275, 0.196), font="F2")
            y = top_y - 16
            for item in list(column.get("items", []) or [])[:4]:
                if not isinstance(item, Mapping):
                    continue
                self.rect(x, y - 30, col_width, 34, (0.141, 0.122, 0.114))
                self.text(x + 6, y - 8, item.get("symbol", ""), size=8, font="F2")
                self.text(x + 6, y - 20, item.get("name", ""), size=7)
                y -= 42
            max_y_drop = max(max_y_drop, top_y - y)
        self.y = top_y - max(max_y_drop, 44) - 12
        edges = list(map_data.get("edges", []) or [])
        for edge in edges[:8]:
            if isinstance(edge, Mapping):
                self.paragraph(f"{edge.get('source', '')} -> {edge.get('target', '')}: {edge.get('relationship', '')}", size=8, max_chars=96, leading=10)

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
            if "relationship_map" in section:
                canvas.relationship_map(section["relationship_map"])
            if "table" in section:
                canvas.table(section["table"])
        else:
            canvas.paragraph(section, size=10)
    return _write_pdf_bytes(canvas.finish(), pathlib.Path(output_path))


def _stylesheet() -> str:
    token_lines = [
        ":root {",
        f"  --base: {REPORT_THEME['base']};",
        f"  --panel: {REPORT_THEME['panel']};",
        f"  --panel-2: {REPORT_THEME['panel_2']};",
        f"  --ink: {REPORT_THEME['ink']};",
        f"  --muted: {REPORT_THEME['muted']};",
        f"  --line: {REPORT_THEME['line']};",
        f"  --accent: {REPORT_THEME['accent']};",
        "  --accent-soft: rgba(255, 70, 50, 0.14);",
        f"  --positive: {REPORT_THEME['positive']};",
        f"  --risk: {REPORT_THEME['risk']};",
        f"  --watch: {REPORT_THEME['watch']};",
        f"  --heading-font: {REPORT_THEME['heading_font']};",
        f"  --body-font: {REPORT_THEME['body_font']};",
        f"  --radius: {REPORT_THEME['radius']};",
        "}",
    ]
    return "\n".join(token_lines) + """
@page {
  size: A4;
  margin: 16mm 13mm;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: #111;
  color: var(--ink);
  font-family: var(--body-font);
  line-height: 1.55;
}
.page {
  max-width: 210mm;
  min-height: 297mm;
  margin: 0 auto;
  padding: 22mm 16mm 24mm;
}
.hero {
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: linear-gradient(145deg, rgba(48,41,39,0.96), rgba(25,20,20,0.92));
  box-shadow: 0 28px 80px rgba(0, 0, 0, 0.32);
  padding: 34px;
  position: relative;
  overflow: hidden;
}
.eyebrow {
  color: var(--accent);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.22em;
  text-transform: uppercase;
}
h1 {
  font-family: var(--heading-font);
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
  border-radius: var(--radius);
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
  border-radius: var(--radius);
  margin-top: 22px;
  padding: 30px;
  page-break-inside: avoid;
}
.report-section:nth-of-type(2n) {
  background: linear-gradient(145deg, rgba(48,41,39,0.92), rgba(25,20,20,0.88));
}
.section-kicker span {
  background: var(--accent-soft);
  border-radius: 4px;
  color: var(--accent);
  display: inline-block;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.14em;
  padding: 6px 10px;
}
h2 {
  font-family: var(--heading-font);
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
.line-chart {
  display: grid;
  gap: 12px;
  margin-top: 18px;
}
.line-chart-svg {
  background: rgba(17, 17, 17, 0.38);
  border: 1px solid var(--line);
  border-radius: 8px;
  width: 100%;
  height: auto;
}
.line-chart-grid {
  stroke: rgba(255, 255, 255, 0.12);
  stroke-width: 1;
}
.line-chart-axis,
.series-label {
  color: var(--muted);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
}
.line-chart-axis {
  fill: var(--muted);
}
.line-chart-axis-line {
  stroke: var(--line);
  stroke-width: 1.5;
}
.line-chart-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 14px;
}
.series-label {
  align-items: center;
  display: inline-flex;
  gap: 8px;
}
.series-swatch {
  border-radius: 999px;
  display: inline-block;
  height: 10px;
  width: 10px;
}
.relationship-map {
  display: grid;
  gap: 18px;
  margin-top: 18px;
}
.map-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}
.map-column {
  border: 1px solid var(--line);
  border-radius: 8px;
  background: rgba(25, 20, 20, 0.72);
  padding: 14px;
}
.map-column h3 {
  color: var(--accent);
  font-size: 12px;
  letter-spacing: 0.12em;
  margin: 0 0 10px;
  text-transform: uppercase;
}
.map-node {
  border-left: 3px solid var(--accent);
  background: rgba(255, 255, 255, 0.045);
  margin-top: 8px;
  min-height: 86px;
  padding: 10px 10px 10px 12px;
}
.map-node strong,
.map-node span,
.map-node em {
  display: block;
}
.map-node strong {
  color: var(--ink);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 13px;
}
.map-node span {
  font-weight: 700;
  margin-top: 4px;
}
.map-node em {
  color: var(--muted);
  font-size: 12px;
  font-style: normal;
  margin-top: 4px;
}
.map-edges {
  border-top: 1px solid var(--line);
  display: grid;
  gap: 8px;
  list-style: none;
  margin: 0;
  padding: 14px 0 0;
}
.map-edges li {
  display: grid;
  gap: 10px;
  grid-template-columns: minmax(120px, 0.7fr) minmax(0, 1fr);
}
.map-edges code {
  color: var(--accent);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
}
.tone-note {
  border-left: 3px solid var(--accent);
  color: var(--muted);
  margin-top: 18px;
  padding-left: 14px;
}
@media print {
  body { background: var(--base); }
  .page { max-width: none; min-height: auto; padding: 0; }
  .hero, .report-section { box-shadow: none; }
}
@media (max-width: 720px) {
  .page { padding: 24px 14px 36px; }
  .hero, .report-section { border-radius: 8px; padding: 22px; }
  h1 { font-size: 36px; }
  h2 { font-size: 24px; }
  .map-grid, .map-edges li { grid-template-columns: 1fr; }
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


def render_html_file_to_pdf_with_chrome(
    html_path: str | pathlib.Path,
    output_path: str | pathlib.Path,
    chrome_binary: str = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
) -> pathlib.Path:
    if os.environ.get("QRD_ENABLE_SYSTEM_CHROME_PDF", "false").strip().lower() != "true":
        raise ReportRenderError(
            "System Chrome PDF rendering is disabled. Set QRD_ENABLE_SYSTEM_CHROME_PDF=true to opt in."
        )
    html_file = pathlib.Path(html_path)
    pdf_path = pathlib.Path(output_path)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    if not html_file.exists():
        raise ReportRenderError(f"HTML companion was not found: {html_file}")
    if not pathlib.Path(chrome_binary).exists():
        raise ReportRenderError(f"Headless Chrome binary was not found at {chrome_binary}.")

    try:
        with tempfile.TemporaryDirectory(prefix="qrd-chrome-") as user_data_dir:
            cmd = [
                chrome_binary,
                "--headless=new",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--allow-file-access-from-files",
                "--no-first-run",
                "--no-default-browser-check",
                "--run-all-compositor-stages-before-draw",
                "--virtual-time-budget=10000",
                f"--user-data-dir={user_data_dir}",
                f"--print-to-pdf={pdf_path}",
                html_file.resolve().as_uri(),
            ]
            subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        stdout = (exc.stdout or "").strip()
        detail = stderr or stdout or str(exc)
        raise ReportRenderError(f"Headless Chrome PDF rendering failed: {detail}") from exc
    except OSError as exc:
        raise ReportRenderError(f"Headless Chrome PDF rendering failed: {exc}") from exc
    return pdf_path


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
