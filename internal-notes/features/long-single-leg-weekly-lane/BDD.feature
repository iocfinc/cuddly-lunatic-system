Feature: Long single-leg weekly resale lane
  Scenario: Bullish stock context surfaces calls only
    Given the stock context is bullish
    When the weekly screen ranks aligned contracts
    Then only CALL contracts should survive for that underlying

  Scenario: Event risk is unknown
    Given the event provider does not return catalyst timing
    When the weekly screen ranks contracts
    Then the contract should stay visible with event_risk set to unknown

  Scenario: Event falls inside holding window
    Given a mapped catalyst sits inside the intended holding window
    When the weekly screen ranks contracts
    Then the contract should remain eligible but carry an event penalty and reviewer caution
