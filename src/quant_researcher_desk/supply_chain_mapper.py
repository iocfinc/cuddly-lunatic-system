"""Evidence-grounded supply-chain mapping for analyst-led sector research."""

from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any


LAYER_ORDER = (
    "eda/ip",
    "wafer fab equipment",
    "process materials",
    "wafer fabrication",
    "packaging/test",
    "memory/substrates",
    "downstream chip/system integration",
)

DEFAULT_MARKETS = ("TW", "US", "NL", "JP", "KR")
DEFAULT_SOURCE_TYPES = ("filing", "official_doc", "industry_report")

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = ROOT / "data" / "supply-chain-mapper"
DEFAULT_CORPUS_PATH = DEFAULT_OUTPUT_ROOT / "pilot_corpus" / "tsmc-fab-output.json"


@dataclass(frozen=True)
class MappingJobRequest:
    artifact_slug: str
    artifact_label: str
    seed_scope: tuple[str, ...]
    max_depth: int
    evidence_policy: str
    markets: tuple[str, ...]
    include_source_types: tuple[str, ...]


@dataclass(frozen=True)
class SupplyNode:
    node_id: str
    label: str
    entity_type: str
    role: str
    layer: int
    country: str
    is_public: bool
    ticker_or_plate: str
    summary: str
    support_evidence_ids: tuple[str, ...] = ()
    confidence_tier: str = "tier_2"


@dataclass(frozen=True)
class SupplyEdge:
    source_id: str
    target_id: str
    relationship_type: str
    direction: str
    confidence_tier: str
    weight_kind: str
    weight_value: str
    evidence_ids: tuple[str, ...]
    assertion_type: str = "confirmed"
    reasoning: str = ""


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    source_type: str
    publisher: str
    url: str
    document_date: str
    retrieved_at: str
    claim_text: str
    entity_refs: tuple[str, ...]
    confidence_tier: str


@dataclass(frozen=True)
class DiscoveryQueueItem:
    topic: str
    why_missing: str
    priority: str
    suggested_source_types: tuple[str, ...]
    status: str


@dataclass(frozen=True)
class MapSnapshotManifest:
    job_id: str
    artifact_slug: str
    created_at: str
    node_count: int
    edge_count: int
    evidence_count: int
    open_questions_count: int
    output_paths: dict[str, str]


@dataclass(frozen=True)
class MappingSnapshot:
    manifest: MapSnapshotManifest
    request: MappingJobRequest
    nodes: tuple[SupplyNode, ...]
    edges: tuple[SupplyEdge, ...]
    evidence: tuple[EvidenceRecord, ...]
    discovery_queue: tuple[DiscoveryQueueItem, ...]
    source_manifest: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class ResearchAudit:
    decision_readiness: str
    coverage_score: int
    layer_counts: dict[str, int]
    tier_counts: dict[str, int]
    publisher_count: int
    confirmed_edge_count: int
    inferred_edge_count: int
    qualitative_edge_count: int
    missing_layers: tuple[str, ...]
    weak_tier1_layers: tuple[str, ...]
    blockers: tuple[str, ...]
    strengths: tuple[str, ...]
    summary: str


@dataclass(frozen=True)
class StressTestResult:
    scenario_name: str
    description: str
    node_count: int
    edge_count: int
    evidence_count: int
    dropped_layers: tuple[str, ...]
    decision_readiness: str
    blockers: tuple[str, ...]


class SupplyChainMapperError(ValueError):
    """Raised when the mapping job cannot be built."""


def default_mapping_request() -> MappingJobRequest:
    return MappingJobRequest(
        artifact_slug="tsmc-fab-output",
        artifact_label="TSMC Leading-Edge Fab Output",
        seed_scope=("wafer fabrication",),
        max_depth=2,
        evidence_policy="tiered_mixed",
        markets=DEFAULT_MARKETS,
        include_source_types=DEFAULT_SOURCE_TYPES,
    )


def build_mapping_snapshot(
    request: MappingJobRequest,
    *,
    now: dt.datetime | None = None,
    corpus_path: Path | None = None,
) -> MappingSnapshot:
    normalized = _normalize_request(request)
    created_at = _timestamp(now)
    corpus = _load_corpus(corpus_path or DEFAULT_CORPUS_PATH)
    nodes_by_id = {node["node_id"]: node for node in corpus["nodes"]}
    claim_bundles = tuple(_filtered_claims(corpus["claims"], normalized))
    selected_node_ids = _discover_reachable_nodes(nodes_by_id, claim_bundles, normalized)

    evidence_records = _collect_evidence(claim_bundles)
    evidence_by_id = {record.evidence_id: record for record in evidence_records}

    node_support: dict[str, set[str]] = {node_id: set() for node_id in selected_node_ids}
    for record in evidence_records:
        for entity_ref in record.entity_refs:
            if entity_ref in node_support:
                node_support[entity_ref].add(record.evidence_id)

    nodes = tuple(
        _build_node(nodes_by_id[node_id], node_support[node_id], evidence_by_id)
        for node_id in sorted(selected_node_ids, key=lambda value: (nodes_by_id[value]["layer"], value))
    )
    visible_node_ids = {node.node_id for node in nodes}

    edges = _collect_edges(claim_bundles, visible_node_ids, evidence_by_id)
    discovery_queue = tuple(_build_discovery_queue(corpus["open_questions"]))
    source_manifest = tuple(_build_source_manifest(evidence_records))

    manifest = MapSnapshotManifest(
        job_id=f"{normalized.artifact_slug}-{_slugify(created_at)}",
        artifact_slug=normalized.artifact_slug,
        created_at=created_at,
        node_count=len(nodes),
        edge_count=len(edges),
        evidence_count=len(evidence_records),
        open_questions_count=len(discovery_queue),
        output_paths={},
    )
    return MappingSnapshot(
        manifest=manifest,
        request=normalized,
        nodes=nodes,
        edges=edges,
        evidence=evidence_records,
        discovery_queue=discovery_queue,
        source_manifest=source_manifest,
    )


def run_mapping_job(
    request: MappingJobRequest,
    *,
    output_root: Path | None = None,
    now: dt.datetime | None = None,
    corpus_path: Path | None = None,
) -> MappingSnapshot:
    snapshot = build_mapping_snapshot(request, now=now, corpus_path=corpus_path)
    artifact_root = (output_root or DEFAULT_OUTPUT_ROOT) / snapshot.request.artifact_slug
    run_dir = artifact_root / "runs" / snapshot.manifest.created_at.replace(":", "-")
    run_dir.mkdir(parents=True, exist_ok=True)

    nodes_path = run_dir / "nodes.json"
    edges_path = run_dir / "edges.json"
    evidence_path = run_dir / "evidence_ledger.json"
    discovery_path = run_dir / "discovery_queue.json"
    source_manifest_path = artifact_root / "source_corpus_index.json"
    backlog_path = artifact_root / "universe_backlog.json"
    explorer_path = run_dir / f"{snapshot.request.artifact_slug}-explorer.html"
    report_path = run_dir / f"{snapshot.request.artifact_slug}-snapshot.md"
    notion_path = run_dir / f"{snapshot.request.artifact_slug}-notion-payload.md"
    audit_path = run_dir / f"{snapshot.request.artifact_slug}-research-audit.md"
    audit_json_path = run_dir / "research_audit.json"
    stress_path = run_dir / "stress_test.json"
    stress_md_path = run_dir / f"{snapshot.request.artifact_slug}-stress-test.md"
    manifest_path = run_dir / "manifest.json"
    audit = build_research_audit(snapshot)
    stress_suite = run_stress_test_suite(request, now=now, corpus_path=corpus_path)

    _write_json(nodes_path, [asdict(node) for node in snapshot.nodes])
    _write_json(edges_path, [asdict(edge) for edge in snapshot.edges])
    _write_json(evidence_path, [asdict(record) for record in snapshot.evidence])
    _write_json(discovery_path, [asdict(item) for item in snapshot.discovery_queue])
    _write_json(source_manifest_path, list(snapshot.source_manifest))
    _write_json(backlog_path, [asdict(item) for item in snapshot.discovery_queue])
    _write_json(audit_json_path, asdict(audit))
    _write_json(stress_path, [asdict(result) for result in stress_suite])
    explorer_path.write_text(_render_explorer(snapshot), encoding="utf-8")
    report_path.write_text(_render_snapshot_report(snapshot), encoding="utf-8")
    audit_path.write_text(_render_research_audit(snapshot, audit), encoding="utf-8")
    stress_md_path.write_text(_render_stress_test_report(snapshot, stress_suite), encoding="utf-8")

    manifest = replace(
        snapshot.manifest,
        output_paths={
            "manifest": str(manifest_path),
            "nodes": str(nodes_path),
            "edges": str(edges_path),
            "evidence_ledger": str(evidence_path),
            "discovery_queue": str(discovery_path),
            "source_corpus_index": str(source_manifest_path),
            "universe_backlog": str(backlog_path),
            "explorer_html": str(explorer_path),
            "report_markdown": str(report_path),
            "notion_payload": str(notion_path),
            "research_audit": str(audit_path),
            "research_audit_json": str(audit_json_path),
            "stress_test": str(stress_path),
            "stress_test_markdown": str(stress_md_path),
        },
    )
    _write_json(manifest_path, asdict(manifest))
    _update_run_history(artifact_root, manifest)
    hydrated_snapshot = replace(snapshot, manifest=manifest)
    notion_path.write_text(_render_notion_payload(hydrated_snapshot), encoding="utf-8")
    return hydrated_snapshot


def _normalize_request(request: MappingJobRequest) -> MappingJobRequest:
    artifact_slug = _slugify(request.artifact_slug)
    artifact_label = request.artifact_label.strip()
    seed_scope = tuple(dict.fromkeys(_normalize_role(value) for value in request.seed_scope if value.strip()))
    markets = tuple(dict.fromkeys(value.strip().upper() for value in request.markets if value.strip()))
    source_types = tuple(dict.fromkeys(value.strip().lower() for value in request.include_source_types if value.strip()))
    if not artifact_slug:
        raise SupplyChainMapperError("artifact_slug is required.")
    if not artifact_label:
        raise SupplyChainMapperError("artifact_label is required.")
    if not seed_scope:
        raise SupplyChainMapperError("seed_scope must include at least one layer.")
    if request.max_depth < 1:
        raise SupplyChainMapperError("max_depth must be at least 1.")
    if not markets:
        raise SupplyChainMapperError("markets must include at least one market.")
    if not source_types:
        raise SupplyChainMapperError("include_source_types must include at least one source type.")
    return MappingJobRequest(
        artifact_slug=artifact_slug,
        artifact_label=artifact_label,
        seed_scope=seed_scope,
        max_depth=request.max_depth,
        evidence_policy=request.evidence_policy.strip() or "tiered_mixed",
        markets=markets,
        include_source_types=source_types,
    )


def _timestamp(now: dt.datetime | None) -> str:
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.timezone.utc)
    return current.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_corpus(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SupplyChainMapperError(f"Corpus file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _filtered_claims(claims: list[dict[str, Any]], request: MappingJobRequest) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for claim in claims:
        markets = {value.upper() for value in claim.get("markets", [])}
        if markets and not (markets & set(request.markets)):
            continue
        evidence = [
            evidence
            for evidence in claim.get("evidence", [])
            if evidence.get("source_type", "").lower() in request.include_source_types
        ]
        if not evidence and claim.get("assertion_type", "confirmed") == "confirmed":
            continue
        selected.append({**claim, "evidence": evidence})
    return selected


def _discover_reachable_nodes(
    nodes_by_id: dict[str, dict[str, Any]],
    claims: tuple[dict[str, Any], ...],
    request: MappingJobRequest,
) -> set[str]:
    seed_ids = {
        node_id
        for node_id, node in nodes_by_id.items()
        if _normalize_role(node["role"]) in request.seed_scope
    }
    if not seed_ids:
        raise SupplyChainMapperError("No nodes matched the requested seed_scope.")

    adjacency: dict[str, set[str]] = {node_id: set() for node_id in nodes_by_id}
    for claim in claims:
        if claim.get("assertion_type", "confirmed") != "confirmed":
            continue
        adjacency.setdefault(claim["source_id"], set()).add(claim["target_id"])
        adjacency.setdefault(claim["target_id"], set()).add(claim["source_id"])

    visited = set(seed_ids)
    frontier = set(seed_ids)
    for _ in range(request.max_depth):
        next_frontier: set[str] = set()
        for node_id in frontier:
            next_frontier.update(adjacency.get(node_id, set()))
        next_frontier -= visited
        visited.update(next_frontier)
        frontier = next_frontier
        if not frontier:
            break
    return visited


def _collect_evidence(claims: tuple[dict[str, Any], ...]) -> tuple[EvidenceRecord, ...]:
    records: dict[str, EvidenceRecord] = {}
    for claim in claims:
        for raw in claim.get("evidence", []):
            record = EvidenceRecord(
                evidence_id=raw["evidence_id"],
                source_type=raw["source_type"],
                publisher=raw["publisher"],
                url=raw["url"],
                document_date=raw["document_date"],
                retrieved_at=raw["retrieved_at"],
                claim_text=raw["claim_text"],
                entity_refs=tuple(raw["entity_refs"]),
                confidence_tier=raw.get("confidence_tier") or _confidence_for_source(raw["source_type"]),
            )
            records.setdefault(record.evidence_id, record)
    return tuple(sorted(records.values(), key=lambda item: item.evidence_id))


def _build_node(
    raw: dict[str, Any],
    support_evidence_ids: set[str],
    evidence_by_id: dict[str, EvidenceRecord],
) -> SupplyNode:
    tiers = [
        evidence_by_id[evidence_id].confidence_tier
        for evidence_id in sorted(support_evidence_ids)
        if evidence_id in evidence_by_id
    ]
    confidence_tier = min(tiers, default="tier_3", key=_tier_rank)
    return SupplyNode(
        node_id=raw["node_id"],
        label=raw["label"],
        entity_type=raw["entity_type"],
        role=raw["role"],
        layer=int(raw["layer"]),
        country=raw["country"],
        is_public=bool(raw["is_public"]),
        ticker_or_plate=raw.get("ticker_or_plate", ""),
        summary=raw["summary"],
        support_evidence_ids=tuple(sorted(support_evidence_ids)),
        confidence_tier=confidence_tier,
    )


def _collect_edges(
    claims: tuple[dict[str, Any], ...],
    visible_node_ids: set[str],
    evidence_by_id: dict[str, EvidenceRecord],
) -> tuple[SupplyEdge, ...]:
    edges: dict[tuple[str, str, str], SupplyEdge] = {}
    for claim in claims:
        source_id = claim["source_id"]
        target_id = claim["target_id"]
        if source_id not in visible_node_ids or target_id not in visible_node_ids:
            continue
        evidence_ids = tuple(
            sorted(
                {
                    evidence["evidence_id"]
                    for evidence in claim.get("evidence", [])
                    if evidence["evidence_id"] in evidence_by_id
                }
            )
        )
        if claim.get("assertion_type", "confirmed") == "confirmed" and not evidence_ids:
            continue
        confidence_tier = min(
            [evidence_by_id[evidence_id].confidence_tier for evidence_id in evidence_ids],
            default=claim.get("confidence_tier", "tier_3"),
            key=_tier_rank,
        )
        edge = SupplyEdge(
            source_id=source_id,
            target_id=target_id,
            relationship_type=claim["relationship_type"],
            direction=claim["direction"],
            confidence_tier=confidence_tier,
            weight_kind=claim.get("weight_kind", "qualitative"),
            weight_value=claim.get("weight_value", "unweighted"),
            evidence_ids=evidence_ids,
            assertion_type=claim.get("assertion_type", "confirmed"),
            reasoning=claim.get("reasoning", ""),
        )
        edges.setdefault((edge.source_id, edge.target_id, edge.relationship_type), edge)
    return tuple(sorted(edges.values(), key=lambda item: (item.source_id, item.target_id, item.relationship_type)))


def _build_discovery_queue(open_questions: list[dict[str, Any]]) -> list[DiscoveryQueueItem]:
    return [
        DiscoveryQueueItem(
            topic=item["topic"],
            why_missing=item["why_missing"],
            priority=item["priority"],
            suggested_source_types=tuple(item["suggested_source_types"]),
            status=item.get("status", "open"),
        )
        for item in open_questions
    ]


def _build_source_manifest(evidence: tuple[EvidenceRecord, ...]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for record in evidence:
        entry = grouped.setdefault(
            record.publisher,
            {
                "publisher": record.publisher,
                "source_types": set(),
                "urls": set(),
                "evidence_ids": [],
                "best_confidence_tier": record.confidence_tier,
            },
        )
        entry["source_types"].add(record.source_type)
        entry["urls"].add(record.url)
        entry["evidence_ids"].append(record.evidence_id)
        if _tier_rank(record.confidence_tier) < _tier_rank(entry["best_confidence_tier"]):
            entry["best_confidence_tier"] = record.confidence_tier
    manifest: list[dict[str, Any]] = []
    for publisher, entry in grouped.items():
        manifest.append(
            {
                "publisher": publisher,
                "source_types": sorted(entry["source_types"]),
                "urls": sorted(entry["urls"]),
                "evidence_ids": sorted(entry["evidence_ids"]),
                "best_confidence_tier": entry["best_confidence_tier"],
            }
        )
    return sorted(manifest, key=lambda item: (item["best_confidence_tier"], item["publisher"]))


def _render_explorer(snapshot: MappingSnapshot) -> str:
    payload = {
        "artifact_label": snapshot.request.artifact_label,
        "created_at": snapshot.manifest.created_at,
        "nodes": [asdict(node) for node in snapshot.nodes],
        "edges": [asdict(edge) for edge in snapshot.edges],
        "evidence": [asdict(record) for record in snapshot.evidence],
        "discovery_queue": [asdict(item) for item in snapshot.discovery_queue],
        "layers": list(LAYER_ORDER),
    }
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_escape(snapshot.request.artifact_label)} Supply Chain Mapping Explorer</title>
  <style>
    :root {{
      --bg: #f5efe7;
      --ink: #191414;
      --panel: #fffaf5;
      --line: #dccbb8;
      --accent: #ff4632;
      --muted: #6f5d53;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: Georgia, "Iowan Old Style", serif; background: radial-gradient(circle at top left, #fffaf5, var(--bg) 55%); color: var(--ink); }}
    header {{ padding: 32px 36px 18px; border-bottom: 1px solid var(--line); }}
    h1 {{ margin: 0 0 8px; font-size: 2rem; }}
    .lede {{ margin: 0; max-width: 72ch; color: var(--muted); }}
    .layout {{ display: grid; grid-template-columns: 1.7fr 1fr; gap: 18px; padding: 24px 24px 40px; }}
    .panel {{ background: rgba(255,250,245,.92); border: 1px solid var(--line); border-radius: 18px; padding: 18px; box-shadow: 0 16px 40px rgba(25,20,20,.06); }}
    .filters {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 16px; }}
    label {{ display: grid; gap: 6px; font-size: .82rem; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); }}
    select {{ padding: 10px 12px; border-radius: 12px; border: 1px solid var(--line); background: white; color: var(--ink); }}
    .layers {{ display: grid; grid-template-columns: repeat(7, minmax(150px, 1fr)); gap: 12px; overflow-x: auto; }}
    .layer {{ min-height: 320px; background: white; border: 1px solid var(--line); border-radius: 14px; padding: 12px; }}
    .layer h2 {{ font-size: 1rem; margin: 0 0 10px; }}
    .node {{ width: 100%; text-align: left; padding: 12px; margin-bottom: 10px; border-radius: 12px; border: 1px solid var(--line); background: var(--panel); cursor: pointer; }}
    .node strong {{ display: block; font-size: .98rem; }}
    .node span {{ display: block; font-size: .84rem; color: var(--muted); margin-top: 4px; }}
    .chip {{ display: inline-block; margin-top: 8px; font-size: .72rem; padding: 4px 8px; border-radius: 999px; background: rgba(255,70,50,.08); color: var(--accent); }}
    .edge-list, .evidence-list, .queue {{ display: grid; gap: 10px; }}
    .edge, .evidence-item, .queue-item {{ padding: 12px; border-radius: 12px; border: 1px solid var(--line); background: white; }}
    .kicker {{ font-size: .78rem; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); margin-bottom: 6px; }}
    a {{ color: var(--accent); }}
    .muted {{ color: var(--muted); }}
    @media (max-width: 1100px) {{
      .layout {{ grid-template-columns: 1fr; }}
      .filters {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Supply Chain Mapping Explorer</h1>
    <p class="lede">Interactive tree and network navigator for {_escape(snapshot.request.artifact_label)}. Click a node to inspect provenance, adjacent relationships, and explicit discovery gaps instead of silently assuming coverage.</p>
  </header>
  <main class="layout">
    <section class="panel">
      <div class="filters" aria-label="Filters">
        <label>Role<select id="roleFilter"><option value="">All roles</option></select></label>
        <label>Geography<select id="countryFilter"><option value="">All geographies</option></select></label>
        <label>Source Tier<select id="sourceFilter"><option value="">All tiers</option></select></label>
        <label>Confidence<select id="confidenceFilter"><option value="">All confidence</option></select></label>
      </div>
      <div class="layers" id="layers"></div>
    </section>
    <aside class="panel">
      <div class="kicker">Snapshot</div>
      <p><strong>{_escape(snapshot.request.artifact_label)}</strong><br><span class="muted">{_escape(snapshot.manifest.created_at)}</span></p>
      <div id="detail">
        <p class="muted">Select a node to inspect evidence and adjacent relationships.</p>
      </div>
      <h2>Open Questions</h2>
      <div class="queue" id="queue"></div>
    </aside>
  </main>
  <script>
    const payload = {json.dumps(payload, ensure_ascii=True)};
    const layersEl = document.getElementById("layers");
    const detailEl = document.getElementById("detail");
    const queueEl = document.getElementById("queue");
    const filters = {{
      role: document.getElementById("roleFilter"),
      country: document.getElementById("countryFilter"),
      source: document.getElementById("sourceFilter"),
      confidence: document.getElementById("confidenceFilter"),
    }};

    const evidenceById = Object.fromEntries(payload.evidence.map(item => [item.evidence_id, item]));
    const nodeEdgeMap = {{}};
    payload.edges.forEach(edge => {{
      [edge.source_id, edge.target_id].forEach(nodeId => {{
        nodeEdgeMap[nodeId] = nodeEdgeMap[nodeId] || [];
        nodeEdgeMap[nodeId].push(edge);
      }});
    }});

    function fillOptions(select, values) {{
      values.forEach(value => {{
        const option = document.createElement("option");
        option.value = value;
        option.textContent = value;
        select.appendChild(option);
      }});
    }}

    fillOptions(filters.role, [...new Set(payload.nodes.map(node => node.role))].sort());
    fillOptions(filters.country, [...new Set(payload.nodes.map(node => node.country))].sort());
    fillOptions(filters.source, [...new Set(payload.evidence.map(record => record.confidence_tier))].sort());
    fillOptions(filters.confidence, [...new Set(payload.nodes.map(node => node.confidence_tier).concat(payload.edges.map(edge => edge.confidence_tier)))].sort());

    Object.values(filters).forEach(select => select.addEventListener("change", render));

    function passesFilters(node) {{
      if (filters.role.value && node.role !== filters.role.value) return false;
      if (filters.country.value && node.country !== filters.country.value) return false;
      if (filters.confidence.value && node.confidence_tier !== filters.confidence.value) return false;
      if (filters.source.value) {{
        const evidenceIds = new Set(node.support_evidence_ids);
        const supported = [...evidenceIds].some(id => evidenceById[id] && evidenceById[id].confidence_tier === filters.source.value);
        if (!supported) return false;
      }}
      return true;
    }}

    function render() {{
      layersEl.innerHTML = "";
      payload.layers.forEach((layerName, index) => {{
        const column = document.createElement("section");
        column.className = "layer";
        column.innerHTML = `<h2>${{layerName}}</h2>`;
        const layerNodes = payload.nodes.filter(node => node.layer === index && passesFilters(node));
        if (!layerNodes.length) {{
          column.innerHTML += '<p class="muted">No nodes match the current filters.</p>';
        }}
        layerNodes.forEach(node => {{
          const button = document.createElement("button");
          button.className = "node";
          button.innerHTML = `<strong>${{node.label}}</strong><span>${{node.country}} · ${{node.entity_type}}</span><span>${{node.summary}}</span><span class="chip">${{node.confidence_tier}}</span>`;
          button.addEventListener("click", () => renderDetail(node));
          column.appendChild(button);
        }});
        layersEl.appendChild(column);
      }});
    }}

    function renderDetail(node) {{
      const edges = (nodeEdgeMap[node.node_id] || []).filter(edge => {{
        if (!filters.confidence.value) return true;
        return edge.confidence_tier === filters.confidence.value;
      }});
      const evidence = node.support_evidence_ids.map(id => evidenceById[id]).filter(Boolean);
      const edgeHtml = edges.map(edge => `<div class="edge"><div class="kicker">${{edge.assertion_type}}</div><strong>${{edge.source_id}} → ${{edge.target_id}}</strong><p>${{edge.relationship_type}}</p><p class="muted">Confidence: ${{edge.confidence_tier}} · Evidence: ${{edge.evidence_ids.join(", ") || "reasoning only"}}</p></div>`).join("");
      const evidenceHtml = evidence.map(item => `<div class="evidence-item"><div class="kicker">${{item.confidence_tier}} · ${{item.source_type}}</div><p>${{item.claim_text}}</p><p><a href="${{item.url}}" target="_blank" rel="noreferrer">${{item.publisher}}</a> · ${{item.document_date}}</p></div>`).join("");
      detailEl.innerHTML = `
        <div class="kicker">${{node.role}}</div>
        <h2>${{node.label}}</h2>
        <p>${{node.summary}}</p>
        <p class="muted">${{node.country}} · ${{node.ticker_or_plate || "private node"}} · ${{node.is_public ? "public" : "private"}}</p>
        <h3>Adjacent Relationships</h3>
        <div class="edge-list">${{edgeHtml || '<p class="muted">No visible relationships in the current filter state.</p>'}}</div>
        <h3>Supporting Evidence</h3>
        <div class="evidence-list">${{evidenceHtml || '<p class="muted">No supporting evidence attached.</p>'}}</div>
      `;
    }}

    queueEl.innerHTML = payload.discovery_queue.map(item => `<div class="queue-item"><div class="kicker">${{item.priority}} · ${{item.status}}</div><strong>${{item.topic}}</strong><p>${{item.why_missing}}</p><p class="muted">Next sources: ${{item.suggested_source_types.join(", ")}}</p></div>`).join("");
    render();
  </script>
</body>
</html>"""


def _render_snapshot_report(snapshot: MappingSnapshot) -> str:
    lines = [
        f"# {snapshot.request.artifact_label} Supply-Chain Snapshot",
        "",
        f"- Created at: {snapshot.manifest.created_at}",
        f"- Nodes: {snapshot.manifest.node_count}",
        f"- Edges: {snapshot.manifest.edge_count}",
        f"- Evidence records: {snapshot.manifest.evidence_count}",
        f"- Open questions: {snapshot.manifest.open_questions_count}",
        "",
        "## Layer Coverage",
    ]
    for layer in LAYER_ORDER:
        labels = [node.label for node in snapshot.nodes if node.role == layer]
        if labels:
            lines.append(f"- {layer}: {', '.join(labels)}")
    lines.extend(["", "## Highest-Confidence Relationships"])
    for edge in snapshot.edges:
        if edge.confidence_tier != "tier_1":
            continue
        lines.append(f"- {edge.source_id} -> {edge.target_id}: {edge.relationship_type} ({edge.confidence_tier})")
    lines.extend(["", "## Discovery Queue"])
    for item in snapshot.discovery_queue:
        lines.append(f"- {item.topic}: {item.why_missing} [{item.priority}]")
    return "\n".join(lines) + "\n"


def build_research_audit(snapshot: MappingSnapshot) -> ResearchAudit:
    layer_counts = {layer: sum(1 for node in snapshot.nodes if node.role == layer) for layer in LAYER_ORDER}
    tier_counts = {
        "tier_1": sum(1 for record in snapshot.evidence if record.confidence_tier == "tier_1"),
        "tier_2": sum(1 for record in snapshot.evidence if record.confidence_tier == "tier_2"),
        "tier_3": sum(1 for record in snapshot.evidence if record.confidence_tier == "tier_3"),
    }
    missing_layers = tuple(layer for layer, count in layer_counts.items() if count == 0)
    weak_tier1_layers = tuple(
        layer
        for layer in LAYER_ORDER
        if layer_counts[layer] > 0
        and not any(
            record.confidence_tier == "tier_1"
            for node in snapshot.nodes
            if node.role == layer
            for evidence_id in node.support_evidence_ids
            for record in [next((item for item in snapshot.evidence if item.evidence_id == evidence_id), None)]
            if record is not None
        )
    )
    confirmed_edge_count = sum(1 for edge in snapshot.edges if edge.assertion_type == "confirmed")
    inferred_edge_count = sum(1 for edge in snapshot.edges if edge.assertion_type == "inferred")
    qualitative_edge_count = sum(1 for edge in snapshot.edges if edge.weight_kind == "qualitative")
    publisher_count = len({record.publisher for record in snapshot.evidence})

    blockers: list[str] = []
    if missing_layers:
        blockers.append(f"Missing coverage in layers: {', '.join(missing_layers)}.")
    if "packaging/test" in weak_tier1_layers:
        blockers.append("Packaging and test coverage is still mostly Tier 2 and not validated by filings or official customer disclosures.")
    if "memory/substrates" in weak_tier1_layers:
        blockers.append("Memory and substrate coverage is still mostly Tier 2 and not validated by Tier 1 supplier evidence.")
    if qualitative_edge_count == len(snapshot.edges):
        blockers.append("No reliable quantitative weighting across the graph; every edge is still qualitative.")
    if any(
        item.priority == "high"
        and ("capacity" in item.topic.lower() or "share allocation" in item.topic.lower())
        for item in snapshot.discovery_queue
    ):
        blockers.append("Named substrate share allocation is unresolved.")
    if any("mix" in item.topic.lower() for item in snapshot.discovery_queue):
        blockers.append("Customer and geography mix is not resolved down to fab-level allocation.")
    if publisher_count < 8:
        blockers.append("Publisher diversity is still too narrow for decision-grade cross-checking.")
    if inferred_edge_count > 0:
        blockers.append("Some cross-layer dependencies remain inferred rather than directly evidenced.")

    strengths: list[str] = []
    if not missing_layers:
        strengths.append("Every target layer in the TSMC fab-output path is represented.")
    if tier_counts["tier_1"] >= 8:
        strengths.append("Core wafer-fabrication dependencies are anchored by a meaningful Tier 1 evidence base.")
    if confirmed_edge_count >= 10:
        strengths.append("The confirmed graph is broad enough to expose multiple upstream and downstream choke points.")
    if publisher_count >= 10:
        strengths.append("The corpus spans enough publishers to support adversarial review instead of single-source narrative reuse.")

    if missing_layers or confirmed_edge_count < 8:
        decision_readiness = "insufficient"
    elif blockers:
        decision_readiness = "directional_only"
    else:
        decision_readiness = "decision_grade"

    coverage_score = max(
        0,
        min(
            100,
            int(
                (len([layer for layer in LAYER_ORDER if layer_counts[layer] > 0]) / len(LAYER_ORDER)) * 45
                + min(tier_counts["tier_1"], 12) * 3
                + min(publisher_count, 12) * 2
                - len(blockers) * 4
            ),
        ),
    )
    summary = (
        f"The map is {decision_readiness.replace('_', ' ')}: it has {confirmed_edge_count} confirmed edges, "
        f"{tier_counts['tier_1']} Tier 1 records, and {publisher_count} unique publishers, but "
        f"{len(blockers)} decision blockers still remain."
    )
    return ResearchAudit(
        decision_readiness=decision_readiness,
        coverage_score=coverage_score,
        layer_counts=layer_counts,
        tier_counts=tier_counts,
        publisher_count=publisher_count,
        confirmed_edge_count=confirmed_edge_count,
        inferred_edge_count=inferred_edge_count,
        qualitative_edge_count=qualitative_edge_count,
        missing_layers=missing_layers,
        weak_tier1_layers=weak_tier1_layers,
        blockers=tuple(blockers),
        strengths=tuple(strengths),
        summary=summary,
    )


def run_stress_test_suite(
    request: MappingJobRequest,
    *,
    now: dt.datetime | None = None,
    corpus_path: Path | None = None,
) -> tuple[StressTestResult, ...]:
    baseline_snapshot = build_mapping_snapshot(request, now=now, corpus_path=corpus_path)
    baseline_layers = {layer for layer in LAYER_ORDER if any(node.role == layer for node in baseline_snapshot.nodes)}
    scenarios = (
        (
            "baseline",
            "Default breadth-first run with mixed evidence tiers and the requested depth.",
            request,
        ),
        (
            "tier1_only",
            "Primary-source-only check to see which parts of the graph survive without Tier 2 support.",
            replace(request, include_source_types=("filing",)),
        ),
        (
            "core_path_only",
            "Shallower recursion test to see what remains if the map is restricted to the immediate fab-output path.",
            replace(request, max_depth=1),
        ),
        (
            "packaging_depth",
            "Packaging-led recursion test from the bottleneck layer outward.",
            replace(request, seed_scope=("packaging/test",), max_depth=max(request.max_depth, 3)),
        ),
    )
    results: list[StressTestResult] = []
    for scenario_name, description, scenario_request in scenarios:
        snapshot = build_mapping_snapshot(scenario_request, now=now, corpus_path=corpus_path)
        audit = build_research_audit(snapshot)
        scenario_layers = {layer for layer in LAYER_ORDER if any(node.role == layer for node in snapshot.nodes)}
        dropped_layers = tuple(sorted(baseline_layers - scenario_layers))
        results.append(
            StressTestResult(
                scenario_name=scenario_name,
                description=description,
                node_count=len(snapshot.nodes),
                edge_count=len(snapshot.edges),
                evidence_count=len(snapshot.evidence),
                dropped_layers=dropped_layers,
                decision_readiness=audit.decision_readiness,
                blockers=audit.blockers,
            )
        )
    return tuple(results)


def _render_research_audit(snapshot: MappingSnapshot, audit: ResearchAudit) -> str:
    lines = [
        f"# {snapshot.request.artifact_label} Research Audit",
        "",
        f"- Decision readiness: {audit.decision_readiness}",
        f"- Coverage score: {audit.coverage_score}/100",
        f"- Confirmed edges: {audit.confirmed_edge_count}",
        f"- Inferred edges: {audit.inferred_edge_count}",
        f"- Tier 1 evidence: {audit.tier_counts['tier_1']}",
        f"- Unique publishers: {audit.publisher_count}",
        "",
        "## Summary",
        audit.summary,
        "",
        "## Strengths",
    ]
    lines.extend(f"- {item}" for item in (audit.strengths or ("No major strengths recorded.",)))
    lines.extend(["", "## Blockers"])
    lines.extend(f"- {item}" for item in (audit.blockers or ("No blocking gaps recorded.",)))
    lines.extend(["", "## Layer Coverage"])
    lines.extend(f"- {layer}: {audit.layer_counts[layer]} nodes" for layer in LAYER_ORDER)
    lines.extend(["", "## Open Questions"])
    lines.extend(f"- {item.topic}: {item.why_missing} [{item.priority}]" for item in snapshot.discovery_queue)
    return "\n".join(lines) + "\n"


def _render_stress_test_report(
    snapshot: MappingSnapshot,
    stress_suite: tuple[StressTestResult, ...],
) -> str:
    lines = [
        f"# {snapshot.request.artifact_label} Stress Test",
        "",
        "The scenarios below test whether the map survives tighter evidence policies and different traversal choices.",
        "",
    ]
    for result in stress_suite:
        lines.extend(
            [
                f"## {result.scenario_name}",
                result.description,
                f"- Decision readiness: {result.decision_readiness}",
                f"- Nodes: {result.node_count}",
                f"- Edges: {result.edge_count}",
                f"- Evidence records: {result.evidence_count}",
                f"- Dropped layers: {', '.join(result.dropped_layers) if result.dropped_layers else 'none'}",
                "- Blockers:",
            ]
        )
        lines.extend(f"  - {item}" for item in result.blockers)
        lines.append("")
    return "\n".join(lines)


def _render_notion_payload(snapshot: MappingSnapshot) -> str:
    audit = build_research_audit(snapshot)
    new_nodes = ", ".join(node.label for node in snapshot.nodes)
    new_edges = ", ".join(f"{edge.source_id}->{edge.target_id}" for edge in snapshot.edges)
    unresolved = "\n".join(f"- {item.topic}: {item.why_missing}" for item in snapshot.discovery_queue)
    links = "\n".join(f"- {key}: {value}" for key, value in snapshot.manifest.output_paths.items())
    return (
        f"# Supply Chain Mapping Run\n\n"
        f"- Date: {snapshot.manifest.created_at}\n"
        f"- Artifact: {snapshot.request.artifact_label}\n"
        f"- Version: {snapshot.manifest.job_id}\n\n"
        f"## New Nodes\n{new_nodes}\n\n"
        f"## New Edges\n{new_edges}\n\n"
        f"## Disproven Hypotheses\n- None in this seed corpus. Track future removals here.\n\n"
        f"## Decision Readiness\n- {audit.decision_readiness}\n- {audit.summary}\n\n"
        f"## Unresolved Questions\n{unresolved}\n\n"
        f"## Next Sources To Inspect\n"
        f"- TSMC annual report and capital spending appendix\n"
        f"- ASE and SPIL advanced packaging disclosures\n"
        f"- Substrate supplier investor decks and capacity commentary\n\n"
        f"## Artifact Links\n{links or '- Manifest paths populate after write.'}\n"
    )


def _update_run_history(artifact_root: Path, manifest: MapSnapshotManifest) -> None:
    history_path = artifact_root / "run_history.json"
    if history_path.exists():
        history = json.loads(history_path.read_text(encoding="utf-8"))
    else:
        history = {"artifact_slug": manifest.artifact_slug, "runs": []}
    history["runs"].append(
        {
            "job_id": manifest.job_id,
            "created_at": manifest.created_at,
            "manifest": manifest.output_paths["manifest"],
            "node_count": manifest.node_count,
            "edge_count": manifest.edge_count,
            "evidence_count": manifest.evidence_count,
        }
    )
    history_path.write_text(json.dumps(history, indent=2), encoding="utf-8")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _normalize_role(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _confidence_for_source(source_type: str) -> str:
    return {
        "filing": "tier_1",
        "official_doc": "tier_1",
        "patent": "tier_1",
        "government_doc": "tier_1",
        "industry_report": "tier_2",
        "news": "tier_2",
        "marketplace": "tier_3",
    }.get(source_type.lower(), "tier_3")


def _tier_rank(value: str) -> int:
    return {"tier_1": 1, "tier_2": 2, "tier_3": 3}.get(value, 9)


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
