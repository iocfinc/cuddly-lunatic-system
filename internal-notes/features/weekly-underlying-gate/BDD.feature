Feature: Weekly underlying gate trace
  Scenario: Symbol fails at stock-context classification
    Given a weekly run where a symbol has no clean bullish or bearish moving-average stack
    When the weekly options screen executes in stock-first mode
    Then the symbol should record a failed `stock_context` gate decision
    And the final outcome should show that the symbol was not shortlisted

  Scenario: Symbol reaches the published shortlist
    Given a weekly run where a symbol passes stock context, weekly expiry, and contract quality
    When the symbol survives ranking and diversification
    Then the symbol should record a passed `shortlist_outcome` gate decision
    And the JSON artifact should include that gate trail
