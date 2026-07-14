---
card_id: math-002
version: 1
when_to_use: "Multi-step calculation problems involving unit conversion, ratios, or percentages where dimensional consistency matters."
match_signals:
  - "percent"
  - "ratio"
  - "per hour / per unit"
  - "convert units"
  - "discount / interest"
pin: match_only
criteria:
  - id: units-consistent
    text: "The final answer includes the correct unit and all conversions are dimensionally consistent."
    severity: must_pass
    impl: llm
  - id: final-number
    text: "The answer states a single, unambiguous final numeric value."
    severity: must_pass
    impl: llm
  - id: rounding-stated
    text: "If rounding occurs, the rounding rule is stated."
    severity: should_pass
    impl: llm
---
The user wants an answer with unambiguous, correct units above stylistic presentation.
Conversion slips and missing units are the dominant failure modes for this task type,
so every step should keep units explicit and check dimensional consistency end to end.
