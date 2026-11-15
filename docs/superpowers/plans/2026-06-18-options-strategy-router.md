# Options Strategy Router Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a stock-first, defined-risk strategy router so the options finder ranks a sane strategy structure instead of defaulting to raw long calls or puts.

**Architecture:** Keep product-specific routing in `naval-analyst`. Add a focused router module that consumes vetted `OptionContract` rows and returns selected/rejected/no-trade strategy evidence. Wire selected strategy fields into weekly and catalyst records, report rows, and tests.

**Tech Stack:** Python dataclasses, existing `OptionContract`, existing weekly/catalyst screen modules, pytest via `uv`.

---

### Task 1: Router Domain Model

**Files:**
- Create: `src/quant_researcher_desk/options_strategy_router.py`
- Test: `tests/test_options_strategy_router.py`

- [ ] **Step 1: Write failing tests**

```python
def test_router_prefers_call_debit_spread_over_expensive_long_call():
    # Build near-spot long call and higher-strike short call.
    # Assert selected structure is call_debit_spread with bounded max loss.

def test_router_rejects_unrealistic_single_leg_breakeven():
    # Build a high-premium long call with breakeven too far from spot.
    # Assert route verdict is no_trade and reason mentions breakeven.

def test_router_can_select_credit_spread_when_iv_is_expensive():
    # Build short put and protective lower put in a bullish context.
    # Assert selected structure is put_credit_spread and net_credit > 0.
```

- [ ] **Step 2: Verify red**

Run: `UV_CACHE_DIR=/tmp/naval-uv-cache PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/uv --cache-dir /tmp/naval-uv-cache run pytest tests/test_options_strategy_router.py -q`

Expected: import/module failure because the router does not exist yet.

- [ ] **Step 3: Implement router**

Create dataclasses for request, leg, candidate, and route. Implement route generation for long option, debit vertical, credit vertical, covered/cash-secured research structures, and no-trade.

- [ ] **Step 4: Verify green**

Run the same focused test command and expect all router tests to pass.

### Task 2: Weekly And Catalyst Integration

**Files:**
- Modify: `src/quant_researcher_desk/weekly_options_screener.py`
- Modify: `src/quant_researcher_desk/catalyst_options_screen.py`
- Test: `tests/test_weekly_options_screener.py`
- Test: `tests/test_catalyst_options_screen.py`

- [ ] **Step 1: Write failing integration tests**

```python
def test_weekly_screened_option_surfaces_selected_strategy():
    # Build fixture weekly result and assert strategy fields exist.

def test_catalyst_idea_surfaces_selected_strategy():
    # Build fixture catalyst result and assert selected strategy is not blank.
```

- [ ] **Step 2: Verify red**

Run the focused weekly/catalyst test targets and expect missing-field failures.

- [ ] **Step 3: Wire router output**

Add strategy fields to `ScreenedOption` and `RankedOptionIdea`; compute routes from vetted contracts; include no-trade reasons in skipped notes.

- [ ] **Step 4: Verify green**

Run focused weekly/catalyst tests and expect pass.

### Task 3: Report Evidence

**Files:**
- Modify: report row builders in `weekly_options_screener.py` and `catalyst_options_screen.py`
- Test: existing report-section tests

- [ ] **Step 1: Write failing report assertions**

Assert ranked tables include selected strategy, net debit/credit, max loss, max profit, breakeven, and router verdict.

- [ ] **Step 2: Implement report fields**

Extend row builders and Telegram text without changing research-only posture.

- [ ] **Step 3: Verify focused tests**

Run focused report and screen tests.

### Task 4: Validation And Linear Closeout

**Files:**
- No production file changes unless validation exposes a bug.

- [ ] **Step 1: Run focused suite**

Run router, options research, weekly, catalyst, lifecycle, shadow replay, and report-script focused tests.

- [ ] **Step 2: Generate fixture artifact**

Run fixture catalyst/weekly outputs and confirm strategy fields are present.

- [ ] **Step 3: Attempt live run**

Run live OpenD screens. If provider rate limits or no trade, record exact blockers.

- [ ] **Step 4: Update Linear**

Add final evidence comment to DIO-76 and mark DIO-77 through DIO-80 done when validation passes.
