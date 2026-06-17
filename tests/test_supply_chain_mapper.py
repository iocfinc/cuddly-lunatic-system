from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quant_researcher_desk.supply_chain_mapper import (  # noqa: E402
    MappingJobRequest,
    build_mapping_snapshot,
    run_mapping_job,
    run_stress_test_suite,
)


def test_build_mapping_snapshot_links_evidence_and_open_questions() -> None:
    snapshot = build_mapping_snapshot(
        MappingJobRequest(
            artifact_slug="tsmc-fab-output",
            artifact_label="TSMC Leading-Edge Fab Output",
            seed_scope=("wafer fabrication",),
            max_depth=2,
            evidence_policy="tiered_mixed",
            markets=("TW", "US", "NL", "JP", "KR"),
            include_source_types=("filing", "official_doc", "industry_report"),
        ),
        now=dt.datetime(2026, 5, 25, 9, 0, tzinfo=dt.timezone.utc),
    )

    manifest = snapshot.manifest
    assert manifest.artifact_slug == "tsmc-fab-output"
    assert manifest.node_count >= 8
    assert manifest.edge_count >= 7
    assert manifest.evidence_count >= 8
    assert manifest.open_questions_count >= 2
    assert any(node.label == "TSMC" and node.role == "wafer fabrication" for node in snapshot.nodes)
    assert any(edge.assertion_type == "inferred" for edge in snapshot.edges)

    tsmc_edge = next(
        edge for edge in snapshot.edges if edge.source_id == "supplier:asml" and edge.target_id == "fab:tsmc"
    )
    assert tsmc_edge.evidence_ids
    assert tsmc_edge.confidence_tier == "tier_1"

    discovery_topics = {item.topic for item in snapshot.discovery_queue}
    assert "Named substrate share allocation" in discovery_topics
    assert "TSMC Arizona downstream customer mix" in discovery_topics


def test_build_mapping_snapshot_dedupes_edges_and_evidence_ids() -> None:
    snapshot = build_mapping_snapshot(
        MappingJobRequest(
            artifact_slug="tsmc-fab-output",
            artifact_label="TSMC Leading-Edge Fab Output",
            seed_scope=("wafer fabrication",),
            max_depth=2,
            evidence_policy="tiered_mixed",
            markets=("TW", "US"),
            include_source_types=("filing",),
        ),
        now=dt.datetime(2026, 5, 25, 9, 0, tzinfo=dt.timezone.utc),
    )

    edge_pairs = [(edge.source_id, edge.target_id, edge.relationship_type) for edge in snapshot.edges]
    assert len(edge_pairs) == len(set(edge_pairs))

    evidence_ids = [record.evidence_id for record in snapshot.evidence]
    assert len(evidence_ids) == len(set(evidence_ids))


def test_run_mapping_job_writes_snapshot_explorer_and_history(tmp_path: pathlib.Path) -> None:
    request = MappingJobRequest(
        artifact_slug="tsmc-fab-output",
        artifact_label="TSMC Leading-Edge Fab Output",
        seed_scope=("wafer fabrication",),
        max_depth=2,
        evidence_policy="tiered_mixed",
        markets=("TW", "US", "NL", "JP", "KR"),
        include_source_types=("filing", "official_doc", "industry_report"),
    )

    first = run_mapping_job(
        request,
        output_root=tmp_path,
        now=dt.datetime(2026, 5, 25, 9, 0, tzinfo=dt.timezone.utc),
    )
    second = run_mapping_job(
        request,
        output_root=tmp_path,
        now=dt.datetime(2026, 5, 26, 9, 0, tzinfo=dt.timezone.utc),
    )

    artifact_root = tmp_path / "tsmc-fab-output"
    history = json.loads((artifact_root / "run_history.json").read_text(encoding="utf-8"))
    assert len(history["runs"]) == 2

    manifest_path = pathlib.Path(first.manifest.output_paths["manifest"])
    explorer_path = pathlib.Path(first.manifest.output_paths["explorer_html"])
    report_path = pathlib.Path(first.manifest.output_paths["report_markdown"])
    payload_path = pathlib.Path(first.manifest.output_paths["notion_payload"])
    evidence_path = pathlib.Path(first.manifest.output_paths["evidence_ledger"])
    audit_path = pathlib.Path(first.manifest.output_paths["research_audit"])
    stress_path = pathlib.Path(first.manifest.output_paths["stress_test"])

    assert manifest_path.exists()
    assert explorer_path.exists()
    assert report_path.exists()
    assert payload_path.exists()
    assert evidence_path.exists()
    assert audit_path.exists()
    assert stress_path.exists()
    assert "Supply Chain Mapping Explorer" in explorer_path.read_text(encoding="utf-8")
    assert "filters" in explorer_path.read_text(encoding="utf-8").lower()
    assert "new edges" in payload_path.read_text(encoding="utf-8").lower()
    assert "decision readiness" in audit_path.read_text(encoding="utf-8").lower()
    assert "tier1_only" in stress_path.read_text(encoding="utf-8")
    assert second.manifest.created_at != first.manifest.created_at


def test_stress_test_suite_flags_baseline_as_directional_not_decision_grade() -> None:
    request = MappingJobRequest(
        artifact_slug="tsmc-fab-output",
        artifact_label="TSMC Leading-Edge Fab Output",
        seed_scope=("wafer fabrication",),
        max_depth=3,
        evidence_policy="tiered_mixed",
        markets=("TW", "US", "NL", "JP", "KR"),
        include_source_types=("filing", "official_doc", "industry_report"),
    )

    results = run_stress_test_suite(
        request,
        now=dt.datetime(2026, 5, 25, 9, 0, tzinfo=dt.timezone.utc),
    )

    assert {result.scenario_name for result in results} == {
        "baseline",
        "tier1_only",
        "core_path_only",
        "packaging_depth",
    }
    baseline = next(result for result in results if result.scenario_name == "baseline")
    tier1_only = next(result for result in results if result.scenario_name == "tier1_only")

    assert baseline.decision_readiness in {"directional_only", "insufficient"}
    assert "Named substrate share allocation is unresolved." in baseline.blockers
    assert tier1_only.edge_count < baseline.edge_count
    assert tier1_only.dropped_layers
