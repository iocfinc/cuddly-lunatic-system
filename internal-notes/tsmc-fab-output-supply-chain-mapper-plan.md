# TSMC Fab-Output Supply Chain Mapper Goal Plan

## Summary

Build a first-pass supply-chain mapping system around **TSMC leading-edge fab output** as the pilot artifact, extending the existing `naval-analyst` sector-tree and reporting surface into a source-grounded recursive mapping workflow.

The v1 goal is analyst-led, not unattended cron expansion:

- gather and normalize evidence from tiered mixed sources
- build a hierarchical supply-chain graph with clickable provenance
- publish an interactive web explorer
- maintain a reusable source and universe repository for later expansion
- write learnings into a dedicated Notion research hub
- package the iterative workflow as a reusable skill in `CodexSkills`

## Defaults

- Pilot artifact: `TSMC fab output`
- Primary UX: interactive tree/network explorer
- Evidence policy: tiered mixed evidence with explicit provenance
- Product implementation lives in `naval-analyst`
- Reusable workflow skill lives in `CodexSkills`
- Learnings ledger is canonical in a dedicated Notion research hub

## Acceptance Focus

- Every displayed edge must trace to evidence.
- Confirmed, inferred, and unresolved relationships must stay visibly distinct.
- The pilot must be reusable for later artifacts such as NVIDIA AI GPUs or AI server racks.
