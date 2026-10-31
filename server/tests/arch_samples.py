"""Shared arch.yaml samples for tests."""

FAN_IN = """\
model: anthropic/claude-haiku-4-5-20251001
flow: |
  input --> a
  input --> b
  a --> judge
  b --> judge
  judge --> output
nodes:
  a: {in: [task], out: [x], prompt: p}
  b: {in: [task], out: [y], prompt: p}
  judge: {in: [x, y], out: [answer], prompt: p%s}
"""

LINEAR_YAML = """\
model: anthropic/claude-haiku-4-5-20251001
flow: |
  input --> draft --> output
nodes:
  draft: {in: [task], out: [answer], prompt: p}
"""

CHECKPOINT_YAML = """\
model: anthropic/claude-haiku-4-5-20251001
flow: |
  input --> draft --> gate
  gate -->|approve| output
  gate -->|reject| output
nodes:
  draft: {in: [task], out: [answer], prompt: p}
  gate: {run: human.checkpoint}
"""

THREE_YAML = """\
model: anthropic/claude-haiku-4-5-20251001
flow: |
  input --> a --> b --> c --> output
nodes:
  a: {in: [task], out: [x], prompt: pa}
  b: {in: [x], out: [y], prompt: pb}
  c: {in: [y], out: [answer], prompt: pc}
"""

LOOP_YAML = """\
model: anthropic/claude-haiku-4-5-20251001
flow: |
  input --> draft --> gate
  gate -->|approve| output
  gate -->|revise| draft
nodes:
  draft: {in: [task], out: [answer], prompt: pd}
  gate: {run: human.checkpoint}
"""
