#!/usr/bin/env python3
"""Build the supply-chain mapper pilot artifacts."""

from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quant_researcher_desk.supply_chain_mapper import (  # noqa: E402
    MappingJobRequest,
    default_mapping_request,
    run_mapping_job,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a supply-chain mapping snapshot and explorer.")
    parser.add_argument("--artifact", default="tsmc-fab-output", help="Artifact slug. Only tsmc-fab-output is seeded in v1.")
    parser.add_argument("--max-depth", type=int, default=2, help="Confirmed-edge traversal depth from the seed layer.")
    parser.add_argument("--output-root", type=pathlib.Path, default=ROOT / "data" / "supply-chain-mapper")
    args = parser.parse_args()

    request = _request_for_artifact(args.artifact, max_depth=args.max_depth)
    snapshot = run_mapping_job(request, output_root=args.output_root)

    print(request.artifact_label)
    print(f"manifest: {snapshot.manifest.output_paths['manifest']}")
    print(f"explorer: {snapshot.manifest.output_paths['explorer_html']}")
    print(f"report: {snapshot.manifest.output_paths['report_markdown']}")
    print(f"notion: {snapshot.manifest.output_paths['notion_payload']}")
    print(f"audit: {snapshot.manifest.output_paths['research_audit']}")
    print(f"stress: {snapshot.manifest.output_paths['stress_test']}")
    return 0


def _request_for_artifact(artifact: str, *, max_depth: int) -> MappingJobRequest:
    if artifact != "tsmc-fab-output":
        raise SystemExit(f"Unsupported artifact: {artifact}")
    request = default_mapping_request()
    return MappingJobRequest(
        artifact_slug=request.artifact_slug,
        artifact_label=request.artifact_label,
        seed_scope=request.seed_scope,
        max_depth=max_depth,
        evidence_policy=request.evidence_policy,
        markets=request.markets,
        include_source_types=request.include_source_types,
    )


if __name__ == "__main__":
    raise SystemExit(main())
