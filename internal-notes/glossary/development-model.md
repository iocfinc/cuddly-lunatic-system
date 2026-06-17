# Spec-Driven Development

## Purpose

Quant Researcher Desk uses a product-local spec-driven workflow so feature intent, technical decisions, executable examples, and review learnings stay close to the code they govern.

This repository-specific meaning of spec-driven development is:

- `WTF`: a short problem-framing note that explains why a feature should exist now.
- `PRD`: the product contract for scope, inputs, outputs, success criteria, and non-goals.
- `ADR`: a durable engineering decision record for choices that are hard to reverse or easy to forget.
- `BDD`: executable behavior examples written in a story format that can be translated into tests.
- `Review Log`: a compact record of review feedback, decisions, and follow-up actions.
- `Evidence Pack`: the generated run artifacts and structured payloads that explain what the workflow did.

## Repository Boundary

- `internal-notes/` is the source of truth for product planning artifacts.
- `docs/` is for rendered, user-facing, or visual artifacts.
- `src/`, `scripts/`, and `tests/` stay focused on product behavior.
- Reusable Codex harness logic belongs outside this repository.

## Working Rules

1. New product milestones should start with a feature pack under `internal-notes/features/`.
2. Tests should map back to BDD scenarios and current product rules.
3. ADRs should be append-only; supersede old choices with a new ADR instead of rewriting history.
4. Generated evidence belongs in run artifacts such as `reports/` or `data/`, not in planning folders.
