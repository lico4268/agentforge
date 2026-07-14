---
card_id: math-001
version: 1
when_to_use: "Natural-language arithmetic word problems that ask for a specific numeric result (counting, money, rates, simple multi-step calculations)."
match_signals:
  - "how many"
  - "how much"
  - "total"
  - "sold / bought / spent / earned"
  - "grade-school math word problem"
pin: match_only
criteria:
  - id: final-number
    text: "The answer states a single, unambiguous final numeric value."
    severity: must_pass
    impl: llm
  - id: answers-the-question
    text: "The final number answers exactly the quantity the question asked for, not an intermediate value."
    severity: must_pass
    impl: llm
  - id: shows-steps
    text: "Intermediate calculation steps are visible."
    severity: should_pass
    impl: llm
---
The user wants the correct final number above all else. Word problems of this type
are self-contained: all required facts are in the problem statement, so clarifying
questions are unnecessary. Brief visible arithmetic is appreciated, but the priority
is one unambiguous numeric answer.
