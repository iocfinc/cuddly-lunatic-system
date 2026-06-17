#!/usr/bin/env python3
"""Generate temporary one-page sector overview assets from the Moomoo universe."""

from __future__ import annotations

import csv
import html
import random
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[1]
NODES_PATH = ROOT / "data" / "sector-universe" / "value_chain_nodes.csv"
EDGES_PATH = ROOT / "data" / "sector-universe" / "value_chain_edges.csv"
OUTPUT_DIR = Path("/tmp/sector-overview-assets")
SEED = 430


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def slug(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "-" for char in value).strip("-").replace("--", "-")


def random_industries(nodes: list[dict[str, str]]) -> list[dict[str, str]]:
    candidates = [
        node
        for node in nodes
        if node["plate_type"] == "INDUSTRY"
        and node["research_priority"] == "1"
        and node["value_chain_role"] in {"upstream", "midstream", "downstream"}
    ]
    random.seed(SEED)
    return random.sample(candidates, 3)


def adjacent_nodes(selected: dict[str, str], nodes: list[dict[str, str]]) -> list[dict[str, str]]:
    roles = ("upstream", "midstream", "downstream", "enabler", "cross_chain")
    domain_nodes = [
        node
        for node in nodes
        if node["market"] == selected["market"]
        and node["domain"] == selected["domain"]
        and node["plate_type"] in {"INDUSTRY", "CONCEPT"}
        and node["value_chain_role"] in roles
    ]
    picked: list[dict[str, str]] = []
    for role in roles:
        role_nodes = sorted(
            [node for node in domain_nodes if node["value_chain_role"] == role],
            key=lambda node: (int(node["research_priority"]), node["name"]),
        )
        picked.extend(role_nodes[:4])
    if selected not in picked:
        picked.append(selected)
    deduped = {node["node_id"]: node for node in picked}
    return list(deduped.values())


def adjacent_edges(selected_nodes: list[dict[str, str]], edges: list[dict[str, str]]) -> list[dict[str, str]]:
    ids = {node["node_id"] for node in selected_nodes}
    return [edge for edge in edges if edge["source_id"] in ids and edge["target_id"] in ids]


def role_counts(nodes: list[dict[str, str]]) -> dict[str, int]:
    roles = ("upstream", "midstream", "downstream", "enabler", "cross_chain")
    return {role: sum(1 for node in nodes if node["value_chain_role"] == role) for role in roles}


def html_page(selected: dict[str, str], nodes: list[dict[str, str]], edges: list[dict[str, str]], mode: str) -> str:
    title = f"{selected['market']} {selected['name']}"
    counts = role_counts(nodes)
    row_limit = 6 if mode == "slide" else 7
    top_nodes = sorted(nodes, key=lambda node: (node["value_chain_role"], int(node["research_priority"]), node["name"]))[:row_limit]
    edge_lines = edges[:5]
    dimensions = {
        "telegram": ("1080px", "1350px", "telegram 4x5 one-pager"),
        "pdf": ("794px", "1123px", "A4 magazine prospectus"),
        "slide": ("1280px", "720px", "PowerPoint 16:9 overview"),
    }[mode]
    width, height, label = dimensions
    role_labels = {
        "upstream": "Upstream",
        "midstream": "Midstream",
        "downstream": "Downstream",
        "enabler": "Enabler",
        "cross_chain": "Cross-chain",
    }
    node_rows = "\n".join(
        f"<div class='node-row'><span>{html.escape(role_labels.get(node['value_chain_role'], node['value_chain_role']))}</span><b>{html.escape(node['name'])}</b><code>{html.escape(node['code'])}</code></div>"
        for node in top_nodes
    )
    edge_rows = "\n".join(
        f"<div class='edge-row'><code>{html.escape(edge['relationship'])}</code><p>{html.escape(edge['rationale'])}</p></div>"
        for edge in edge_lines
    ) or "<div class='edge-row'><code>Evidence queue</code><p>No direct graph edge yet. Use Moomoo constituents and filings to source supplier, channel, or demand transmission evidence.</p></div>"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)} {html.escape(label)}</title>
  <style>
    :root {{
      --bg: #1a1a1a;
      --ink: #f4f1eb;
      --muted: #aaa39a;
      --faint: #756f67;
      --line: rgba(255,255,255,.14);
      --line2: rgba(255,255,255,.24);
      --accent: #ff4632;
      --amber: #fedc2a;
      --panel: rgba(255,255,255,.045);
      --mono: "JetBrains Mono", "SFMono-Regular", Menlo, Consolas, monospace;
      --sans: "Geist", "Satoshi", "Avenir Next", system-ui, sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      width: {width};
      min-height: {height};
      background: var(--bg);
      color: var(--ink);
      font-family: var(--sans);
    }}
    .page {{
      position: relative;
      width: {width};
      height: {height};
      overflow: hidden;
      padding: {("58px 58px 48px" if mode == "telegram" else "42px 54px" if mode == "slide" else "52px 56px")};
      background:
        radial-gradient(circle at 18% 31%, rgba(255,70,50,.19), transparent 300px),
        linear-gradient(180deg, rgba(255,255,255,.035), transparent 45%),
        #1a1a1a;
    }}
    .page::before {{
      content: "";
      position: absolute;
      inset: 0;
      pointer-events: none;
      opacity: .15;
      background-image: linear-gradient(rgba(255,255,255,.055) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.04) 1px, transparent 1px);
      background-size: 42px 42px;
      mask-image: linear-gradient(to bottom, black, transparent 84%);
    }}
    .masthead {{
      position: relative;
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 28px;
      align-items: start;
      border-bottom: 1px solid var(--line2);
      padding-bottom: 26px;
    }}
    .kicker {{
      color: var(--accent);
      font: 12px/1 var(--mono);
      text-transform: uppercase;
      margin-bottom: 18px;
    }}
    h1 {{
      margin: 0;
      max-width: {("720px" if mode == "telegram" else "650px" if mode == "slide" else "560px")};
      font-size: {("82px" if mode == "telegram" else "64px" if mode == "slide" else "58px")};
      line-height: .9;
      letter-spacing: -0.055em;
      font-weight: 760;
    }}
    .code-box {{
      border-left: 1px solid var(--line2);
      padding-left: 22px;
      color: var(--muted);
      font: 14px/1.6 var(--mono);
      text-align: right;
    }}
    .thesis {{
      position: relative;
      display: grid;
      grid-template-columns: {("1.1fr .9fr" if mode == "telegram" else "1.05fr .95fr")};
      gap: 34px;
      padding: {("42px 0 26px" if mode == "telegram" else "24px 0 18px" if mode == "slide" else "34px 0 22px")};
      border-bottom: 1px solid var(--line);
    }}
    .lede {{
      color: var(--muted);
      font-size: {("28px" if mode == "telegram" else "18px" if mode == "slide" else "20px")};
      line-height: 1.35;
      letter-spacing: -0.02em;
    }}
    .metrics {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      border-top: 1px solid var(--line);
      border-left: 1px solid var(--line);
    }}
    .metric {{
      min-height: {("118px" if mode == "telegram" else "70px" if mode == "slide" else "86px")};
      padding: 16px;
      border-right: 1px solid var(--line);
      border-bottom: 1px solid var(--line);
    }}
    .metric b {{
      display: block;
      font: {("42px" if mode == "telegram" else "28px" if mode == "slide" else "31px")}/1 var(--mono);
      color: var(--ink);
      font-weight: 560;
    }}
    .metric span {{
      display: block;
      margin-top: 12px;
      color: var(--faint);
      font: 12px/1.25 var(--mono);
      text-transform: uppercase;
    }}
    .body-grid {{
      position: relative;
      display: grid;
      grid-template-columns: {("1fr" if mode == "telegram" else "1.05fr .95fr")};
      gap: {("28px" if mode != "slide" else "34px")};
      padding-top: {("26px" if mode != "slide" else "18px")};
    }}
    .section-label {{
      color: var(--faint);
      font: 12px/1 var(--mono);
      text-transform: uppercase;
      margin-bottom: 14px;
    }}
    .node-row {{
      display: grid;
      grid-template-columns: {("132px 1fr 150px" if mode == "telegram" else "92px 1fr 118px")};
      gap: 14px;
      align-items: baseline;
      min-height: {("54px" if mode == "telegram" else "34px" if mode == "slide" else "40px")};
      border-top: 1px solid var(--line);
      padding: {("12px 0" if mode != "slide" else "9px 0")};
    }}
    .node-row span,
    .node-row code {{
      color: var(--faint);
      font: 12px/1 var(--mono);
      text-transform: uppercase;
    }}
    .node-row b {{
      font-size: {("21px" if mode == "telegram" else "13px" if mode == "slide" else "15px")};
      letter-spacing: -0.02em;
    }}
    .edge-row {{
      border-top: 1px solid var(--line);
      padding: 13px 0;
    }}
    .edge-row code {{
      color: var(--amber);
      font: 12px/1 var(--mono);
      text-transform: uppercase;
    }}
    .edge-row p {{
      margin: 8px 0 0;
      color: var(--muted);
      font-size: {("18px" if mode == "telegram" else "12px" if mode == "slide" else "13px")};
      line-height: 1.45;
    }}
    .footer {{
      position: absolute;
      left: {("58px" if mode == "telegram" else "54px" if mode == "slide" else "56px")};
      right: {("58px" if mode == "telegram" else "54px" if mode == "slide" else "56px")};
      bottom: {("40px" if mode == "telegram" else "28px" if mode == "slide" else "34px")};
      display: flex;
      justify-content: space-between;
      border-top: 1px solid var(--line2);
      padding-top: 16px;
      color: var(--faint);
      font: 12px/1 var(--mono);
      text-transform: uppercase;
    }}
  </style>
</head>
<body>
  <main class="page">
    <header class="masthead">
      <div>
        <div class="kicker">Sector overview · {html.escape(label)}</div>
        <h1>{html.escape(title)}</h1>
      </div>
      <div class="code-box">{html.escape(selected['code'])}<br>{html.escape(selected['domain'])}<br>{html.escape(selected['value_chain_role']).replace("_", " ")}</div>
    </header>
    <section class="thesis">
      <div class="lede">{html.escape(selected['name'])} sits inside {html.escape(selected['domain'])}. Treat this as a supply-chain field note: map the layer, identify neighboring plates, then replace heuristic edges with sourced constituent evidence.</div>
      <div class="metrics">
        <div class="metric"><b>{len(nodes)}</b><span>Plates mapped</span></div>
        <div class="metric"><b>{len(edges)}</b><span>Starter edges</span></div>
        <div class="metric"><b>{counts['upstream']}</b><span>Upstream</span></div>
        <div class="metric"><b>{counts['midstream'] + counts['downstream']}</b><span>Operating demand</span></div>
      </div>
    </section>
    <section class="body-grid">
      <div>
        <div class="section-label">Value-chain plates</div>
        {node_rows}
      </div>
      <div>
        <div class="section-label">Evidence queue</div>
        {edge_rows}
      </div>
    </section>
    <footer class="footer">
      <span>Quant Researcher Desk</span>
      <span>Research only · Moomoo plate taxonomy</span>
    </footer>
  </main>
</body>
</html>"""


def pptx_xml_escape(value: str) -> str:
    return escape(value, {"'": "&apos;", '"': "&quot;"})


def tx_box(x: int, y: int, cx: int, cy: int, text: str, size: int, color: str = "F4F1EB", bold: bool = False) -> str:
    bold_attr = ' b="1"' if bold else ""
    paras = "".join(
        f'<a:p><a:r><a:rPr lang="en-US" sz="{size}"{bold_attr}><a:solidFill><a:srgbClr val="{color}"/></a:solidFill></a:rPr><a:t>{pptx_xml_escape(line)}</a:t></a:r></a:p>'
        for line in text.split("\n")
    )
    return f"""<p:sp><p:nvSpPr><p:cNvPr id="{abs(hash((x,y,text))) % 200000 + 10}" name="Text"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/><a:ln><a:noFill/></a:ln></p:spPr><p:txBody><a:bodyPr wrap="square" anchor="t"/><a:lstStyle/>{paras}</p:txBody></p:sp>"""


def rect(x: int, y: int, cx: int, cy: int, fill: str, line: str = "3A3835") -> str:
    return f"""<p:sp><p:nvSpPr><p:cNvPr id="{abs(hash((x,y,cx,cy))) % 200000 + 300000}" name="Shape"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:solidFill><a:srgbClr val="{fill}"/></a:solidFill><a:ln w="9525"><a:solidFill><a:srgbClr val="{line}"/></a:solidFill></a:ln></p:spPr></p:sp>"""


def make_pptx(path: Path, selected: dict[str, str], nodes: list[dict[str, str]], edges: list[dict[str, str]]) -> None:
    title = f"{selected['market']} {selected['name']}"
    counts = role_counts(nodes)
    node_names = "\n".join(f"{node['value_chain_role'].replace('_', ' ').title()}  {node['name']}" for node in nodes[:6])
    edge_note = edges[0]["rationale"] if edges else "No direct graph edge yet. Source constituents and filings before treating the relationship as evidence."
    shapes = [
        rect(0, 0, 12192000, 6858000, "1A1A1A", "1A1A1A"),
        rect(460000, 5250000, 11270000, 18000, "FF4632", "FF4632"),
        tx_box(560000, 410000, 6600000, 980000, title, 4300, bold=True),
        tx_box(7900000, 520000, 3200000, 600000, f"{selected['code']}\n{selected['domain']}\n{selected['value_chain_role'].replace('_', ' ')}", 1250, "AAA39A"),
        tx_box(580000, 1750000, 5200000, 950000, f"{selected['name']} is a one-page supply-chain overview. Map the layer, inspect adjacent plates, and move from heuristic relationships to sourced evidence.", 1650, "AAA39A"),
        rect(6600000, 1600000, 1950000, 860000, "22211F"),
        rect(8550000, 1600000, 1950000, 860000, "22211F"),
        rect(6600000, 2460000, 1950000, 860000, "22211F"),
        rect(8550000, 2460000, 1950000, 860000, "22211F"),
        tx_box(6810000, 1780000, 1500000, 360000, str(len(nodes)), 2700, bold=True),
        tx_box(8760000, 1780000, 1500000, 360000, str(len(edges)), 2700, bold=True),
        tx_box(6810000, 2640000, 1500000, 360000, str(counts["upstream"]), 2700, bold=True),
        tx_box(8760000, 2640000, 1500000, 360000, str(counts["midstream"] + counts["downstream"]), 2700, bold=True),
        tx_box(6810000, 2210000, 1500000, 240000, "PLATES", 850, "756F67"),
        tx_box(8760000, 2210000, 1500000, 240000, "EDGES", 850, "756F67"),
        tx_box(6810000, 3070000, 1500000, 240000, "UPSTREAM", 850, "756F67"),
        tx_box(8760000, 3070000, 1500000, 240000, "OPERATING DEMAND", 850, "756F67"),
        tx_box(580000, 3420000, 4700000, 1700000, node_names, 1050, "F4F1EB"),
        tx_box(6600000, 3720000, 4300000, 900000, edge_note, 1200, "AAA39A"),
        tx_box(560000, 5900000, 5000000, 240000, "Quant Researcher Desk", 850, "756F67"),
        tx_box(8000000, 5900000, 3300000, 240000, "Research only · Moomoo plate taxonomy", 850, "756F67"),
    ]
    slide_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:cSld><p:bg><p:bgPr><a:solidFill><a:srgbClr val="1A1A1A"/></a:solidFill><a:effectLst/></p:bgPr></p:bg><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>{''.join(shapes)}</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>"""
    files = {
        "[Content_Types].xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/><Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/></Types>""",
        "_rels/.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/></Relationships>""",
        "ppt/presentation.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst><p:sldSz cx="12192000" cy="6858000" type="wide"/><p:notesSz cx="6858000" cy="9144000"/></p:presentation>""",
        "ppt/_rels/presentation.xml.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/></Relationships>""",
        "ppt/slides/slide1.xml": slide_xml,
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    nodes = read_csv(NODES_PATH)
    edges = read_csv(EDGES_PATH)
    manifest = []
    for selected in random_industries(nodes):
        selection = adjacent_nodes(selected, nodes)
        selection_edges = adjacent_edges(selection, edges)
        base = f"{slug(selected['market'])}-{slug(selected['name'])}"
        telegram_html = OUTPUT_DIR / f"{base}-telegram.html"
        pdf_html = OUTPUT_DIR / f"{base}-prospectus.html"
        slide_html = OUTPUT_DIR / f"{base}-overview-16x9.html"
        pptx_path = OUTPUT_DIR / f"{base}-overview.pptx"
        telegram_html.write_text(html_page(selected, selection, selection_edges, "telegram"), encoding="utf-8")
        pdf_html.write_text(html_page(selected, selection, selection_edges, "pdf"), encoding="utf-8")
        slide_html.write_text(html_page(selected, selection, selection_edges, "slide"), encoding="utf-8")
        make_pptx(pptx_path, selected, selection, selection_edges)
        manifest.append(
            {
                "market": selected["market"],
                "industry": selected["name"],
                "code": selected["code"],
                "telegram_html": str(telegram_html),
                "pdf_html": str(pdf_html),
                "slide_html": str(slide_html),
                "pptx": str(pptx_path),
            }
        )
    manifest_path = OUTPUT_DIR / "manifest.csv"
    with manifest_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(manifest[0]))
        writer.writeheader()
        writer.writerows(manifest)
    print(f"wrote {len(manifest)} asset sets to {OUTPUT_DIR}")
    for item in manifest:
        print(f"{item['market']} {item['industry']} -> {item['pptx']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
