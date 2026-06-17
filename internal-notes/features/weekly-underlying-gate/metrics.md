# Metrics: Weekly Underlying Gate Trace

## Feature Metrics

- Primary metric: percentage of attempted symbols with a complete final gate outcome in the JSON artifact
- Guardrail metric: no regression in existing weekly artifact generation or Notion sync
- Failure indicator: stage-specific failures become impossible to distinguish from final shortlist omission

## Evidence Sources

- Structured payload: weekly shortlist JSON `gate_results` and `gate_summary`
- Human-facing artifact: weekly HTML `Gate Trace` section
- Test or fixture evidence: weekly screener, script, and journal sync tests
