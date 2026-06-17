# TSMC Fab Output Decision-Grade Thesis Goal

## `/goal`

Build a decision-grade supply-chain thesis program for TSMC fab output that identifies bottlenecks, monopolies, and researchable positions, produces Notion-synced visual artifacts, and hands a ranked opportunity set into TradingAgents for deeper security analysis.

## Role

Operate as an Analyst, not a feature implementer. The job is to determine whether the current research is sufficient to support supply-chain judgment, then push until the remaining gaps are explicit, ranked, and actionable.

## Governing Question

Which parts of the TSMC leading-edge output chain have the highest combination of:

- bottleneck power
- scarcity or monopoly traits
- pricing leverage
- strategic substitution difficulty
- clean public-equity researchability for follow-through in TradingAgents

## Why This Goal Exists

The first mapper proved the system can produce an evidence-linked graph. It did **not** prove the graph is enough for decisions.

The next session must close that gap by treating the graph as a thesis engine and asking:

1. What survives under a harsh evidence policy?
2. Which chokepoints remain under-proven?
3. Which public companies actually sit on the economic bottlenecks?
4. Which names deserve a full TradingAgents research packet?

## Decision Standard

The work is only "decision-grade" when all of the following are true:

- The map distinguishes structural bottlenecks from crowded participants.
- At least the key bottleneck edges are backed by primary-source or clearly attributable official evidence.
- The economic mechanism is explicit: capacity, switching cost, share concentration, qualification friction, yield sensitivity, or geopolitical dependence.
- The link from supply-chain bottleneck to public equity thesis is legible.
- The remaining uncertainty is bounded enough to know what matters next.

If that standard is not met, the output must say so plainly and name the missing proof.

## Research Lanes

### 1. Bottleneck Proof

Focus on whether the chain is genuinely constrained at:

- EUV lithography
- advanced process materials
- advanced packaging / CoWoS
- HBM integration
- ABF substrate supply
- ATMP handoff
- geographic capacity concentration

For each lane, answer:

- what is the actual choke point?
- who controls it?
- how hard is substitution?
- what evidence is primary versus narrative?

### 2. Monopoly and Oligopoly Structure

For each critical lane, classify the market shape:

- monopoly
- duopoly
- oligopoly
- fragmented

Then explain why:

- process qualification barriers
- customer lock-in
- capex intensity
- IP moat
- tooling uniqueness
- regulatory or geopolitical barrier

### 3. Equity Translation

Translate supply-chain conclusions into a public-market shortlist:

- direct bottleneck owner
- second-order beneficiary
- over-owned narrative name with weak bottleneck ownership
- high-importance but low-investability private or opaque node

Every shortlisted ticker needs:

- thesis hook
- supply-chain role
- dependence on the bottleneck
- what would invalidate the thesis

### 4. TradingAgents Handoff

Only hand names into TradingAgents after the supply-chain case is explicit.

For each candidate name, prepare:

- ticker
- why this name matters in the chain
- what bottleneck it owns or depends on
- what evidence supports the linkage
- what the market might be underpricing
- what follow-up questions TradingAgents should test

## Required Outputs

### Product-repo outputs in `naval-analyst`

- updated supply-chain graph snapshot
- expanded evidence ledger
- research audit
- stress-test report
- bottleneck scoreboard
- monopoly / oligopoly scoreboard
- TradingAgents candidate watchlist
- HTML thesis dashboard suitable for Notion sync or embed

### Notion outputs

- one program page under `Supply Chain Mapping`
- one run log per major evidence refresh
- one page that acts as the analyst control room:
  - bottlenecks
  - monopolies
  - candidate tickers
  - open proof gaps
  - next source targets

## Priority Questions

The next session should push these first:

1. CoWoS outbound allocation by customer
2. named substrate share allocation
3. TSMC Arizona customer and product-family mix
4. ASE vs Amkor vs internal TSMC packaging handoff by product family
5. HBM integration dependence around NVIDIA and AMD
6. whether the "winning" equity names are actually bottleneck owners or just narrative passengers

## Stop Conditions

Do **not** claim thesis completion if:

- the key chokepoints are still only qualitative
- primary sources do not materially support the bottleneck story
- the equity translation is just "important company in the ecosystem"
- the strongest candidates are still under-specified

## Success Condition

The session succeeds when it can produce:

1. a ranked list of bottlenecks
2. a ranked list of investable public names connected to those bottlenecks
3. a clear statement of what is known, inferred, and still unproven
4. a clean TradingAgents handoff set for the best names

## First Candidate Universe

Start from the currently visible map and expect it to expand:

- TSMC
- ASML
- Applied Materials
- Cadence
- Synopsys
- SUMCO
- ASE
- Amkor
- SK hynix
- Unimicron
- Nan Ya PCB
- NVIDIA
- AMD
- Apple

## Operating Note

Default tone: restrained, evidence-dense, and explicit about where the thesis is still weak.
