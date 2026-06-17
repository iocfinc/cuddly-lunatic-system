# ADR-001: Product Artifact Boundaries For Weekly Gate Trace

## Status

Accepted

## Context

The weekly gate-trace milestone adds both product-planning material and new rendered outputs. The repository needs a clear rule for where those artifacts belong so product notes, generated reports, and reusable automation do not drift together.

## Decision

- Store product-planning artifacts for this milestone under `internal-notes/features/weekly-underlying-gate/`.
- Keep `docs/` reserved for user-facing visual or rendered artifacts.
- Keep reusable harness logic, generalized Codex workflows, and non-product automation outside `naval-analyst`.

## Consequences

- Positive:
  - product intent stays next to the repo that owns the workflow
  - rendered outputs remain easy to browse without mixing with planning notes
  - repo boundaries stay aligned with `AGENTS.md`
- Negative:
  - some context will still live outside the repo when it becomes reusable
- Follow-up:
  - future weekly-screen milestones should add new ADRs instead of rewriting this one
