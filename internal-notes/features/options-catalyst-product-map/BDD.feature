Feature: Options Catalyst product loop
  Scenario: Historical replay blocks sparse option marks
    Given a catalyst option idea has fewer than five daily option marks
    When the historical replay runner evaluates the idea
    Then the backtest status should be `blocked_missing_data`
    And the advisor gate should not allow promotion beyond `conditional_watch`

  Scenario: Paper lifecycle requires exit rules before activation
    Given a catalyst option idea has passed stock-first and contract-quality gates
    When the idea is moved from `screened` to `paper_accepted`
    Then the record should include a DTE floor, thesis invalidation, premium drawdown, and premium target rule
    And missing rules should keep the idea out of `paper_active`

  Scenario: Persona council cannot override deterministic blockers
    Given the Regime Analyst and Contract Specialist mark an idea as `priority_review`
    And the historical replay status is `blocked_missing_data`
    When the persona council summary is built
    Then the final disposition should be no higher than `conditional_watch`
    And the blocker should name the missing historical replay evidence

  Scenario: GPT persona disagreement is captured as product evidence
    Given at least two personas disagree on an option idea
    When the review artifact is written
    Then the artifact should preserve each persona disposition
    And the summary should include the disagreement reason without converting it into a trade instruction

  Scenario: Post-review attribution records what mattered
    Given a paper idea has closed
    When post-review attribution runs
    Then the artifact should record whether stock regime, contract selection, catalyst timing, and exit rule helped or hurt
    And the lesson should remain research-only

