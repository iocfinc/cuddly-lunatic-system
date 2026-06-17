#!/usr/bin/env python3
"""Build a catalyst options screen with lifecycle review and advisor grading."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from quant_researcher_desk.catalyst_lifecycle import (  # noqa: E402
    advisor_report_sections,
    artifact_payload,
    build_advisor_deliberation,
    build_lifecycle_reviews,
    build_screen_artifact,
    catalyst_records_from_report,
)
from quant_researcher_desk.catalyst_options_screen import (  # noqa: E402
    DEFAULT_CANDIDATES,
    FixtureCatalystOptionsProvider,
    build_catalyst_options_screen,
    catalyst_report_sections,
)
from quant_researcher_desk.moomoo_options_report import MoomooOpenDQuoteClient  # noqa: E402
from quant_researcher_desk.reporting import render_pdf_report, write_html_report  # noqa: E402
from scripts.telegram_notify import load_env  # noqa: E402


def main() -> int:
    env = load_env(ROOT / ".env.example")
    env.update(load_env(ROOT / ".env"))

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", action="store_true", help="Use deterministic local fixture data instead of OpenD.")
    parser.add_argument("--dry-run", action="store_true", help="Print artifact paths and advisor result without posting.")
    parser.add_argument("--output-dir", type=pathlib.Path, default=ROOT / "reports" / "catalyst-options-review")
    parser.add_argument("--opend-host", default=env.get("MOOMOO_OPEND_HOST", "127.0.0.1"))
    parser.add_argument("--opend-port", type=int, default=int(env.get("MOOMOO_OPEND_PORT", "11111")))
    args = parser.parse_args()

    try:
        if args.fixture:
            provider = FixtureCatalystOptionsProvider()
            report = build_catalyst_options_screen(provider, DEFAULT_CANDIDATES)
        else:
            with MoomooOpenDQuoteClient(host=args.opend_host, port=args.opend_port) as client:
                report = build_catalyst_options_screen(client, DEFAULT_CANDIDATES)
    except Exception as exc:
        print(f"catalyst options review failed: {exc}", file=sys.stderr)
        return 1

    records = catalyst_records_from_report(report)
    lifecycle_reviews = build_lifecycle_reviews(records)
    artifact = build_screen_artifact(report, records, lifecycle_reviews)
    deliberation = build_advisor_deliberation(artifact)

    timestamp = report.generated_at.strftime("%Y%m%d-%H%M%S")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / f"{timestamp}-catalyst-options-review.json"
    html_path = args.output_dir / f"{timestamp}-catalyst-options-review.html"
    pdf_path = args.output_dir / f"{timestamp}-catalyst-options-review.pdf"
    sections = [
        *catalyst_report_sections(report),
        *advisor_report_sections(artifact, deliberation),
    ]
    metadata = {
        "generated_at": report.generated_at.strftime("%Y-%m-%d %H:%M:%S %Z").strip(),
        "universe": len(report.candidates),
        "ranked_ideas": len(report.ideas),
        "advisor_verdict": deliberation.verdict,
        "advisor_score": deliberation.score,
    }
    json_path.write_text(json.dumps(artifact_payload(artifact, deliberation), indent=2), encoding="utf-8")
    write_html_report("Catalyst Options Review", sections, metadata, html_path)
    render_pdf_report("Catalyst Options Review", sections, metadata, pdf_path, html_companion_path=html_path)

    print("Catalyst Options Review")
    print(f"screen-json: {json_path}")
    print(f"report-html: {html_path}")
    print(f"report-pdf: {pdf_path}")
    print(f"ranked-ideas: {len(report.ideas)}")
    print(f"advisor-verdict: {deliberation.verdict}")
    print(f"advisor-score: {deliberation.score}")
    if deliberation.blockers:
        print(f"advisor-blockers: {', '.join(deliberation.blockers)}")
    if deliberation.verdict != "PASS":
        return 1
    if args.dry_run:
        print("dry-run: no Telegram delivery attempted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
