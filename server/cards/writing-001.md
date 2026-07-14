---
card_id: writing-001
version: 1
when_to_use: "Prose production tasks such as summarizing, drafting, rewriting, or tone adjustment."
match_signals:
  - "summarize"
  - "rewrite"
  - "draft"
  - "tone"
pin: match_only
criteria:
  - id: covers-key-points
    text: "The output covers every key point of the source/request without inventing facts."
    severity: must_pass
    impl: llm
  - id: length-respected
    text: "Stated length or format constraints are respected."
    severity: should_pass
    impl: llm
---
The user prioritizes factual fidelity over stylistic polish for this kind of task.
Invented facts or dropped key points are worse than a less polished sentence, so
accuracy of content must come first and length constraints second.
