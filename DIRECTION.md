# Current direction (source of truth)

> Last updated: 2026-11-01. **This document takes precedence over every other design document.**
> If another document conflicts with this one, that document is out of date.

## 1. What we are building

**Claude Code designs; AgentForge runs it cheaply, repeatedly, and measurably.**

AgentForge turns a short `arch.yaml` into a runnable LangGraph pipeline. The main way to use it
is from inside Claude Code: the user asks for a pipeline, Claude writes `server/arch/*.yaml`,
runs it with the headless `agentforge` CLI, asks the user in chat when a human checkpoint
pauses the run, and reports the result. The browser dashboard stays as an optional viewer.

AgentForge is only worth using where Claude Code alone is weak:

| Strength | Why Claude Code can't do it alone |
|---|---|
| A model per node (non-Claude and local models included) | Claude Code subagents only run Claude models |
| The pipeline is a file | Re-run it, diff it, run it from cron/CI without a Claude Code session |
| **Replay from a middle node** | Change a late prompt and re-run from there; earlier steps cost nothing |
| **Comparison reports** | Same input, two variants, per-node cost and success side by side |
| Per-node OS isolation | Claude Code's sandbox is per session, not per step |

A one-off task ("research this and write a doc") is faster done directly in Claude Code. The
skill says so, so Claude does not reach for a pipeline when one is not needed.

Not in scope: marketplace packaging, supporting agents other than Claude Code, Claude Code
standing in for nodes (nodes run on the model written in the YAML), deleting the dashboard.

Authoring is text. The diagram (mermaid) is a read-only artifact generated from `flow:`; the
old node canvas was retired on 2026-09-02.

## 2. We do not fix node roles

- We do **not hard-code roles** such as "reviewer" or "planner" into node types. The user
  defines a node's role through its name, prompt, and `in`/`out` keys in `arch.yaml`.
- Branch names (`accept`/`refine`/`clarify`, `approve`/`revise`/`reject`) are **examples,
  not a contract.** Users must be able to create branches with any count and any names.
- What we provide is **the switch as a mechanism**, not the meaning of the switch.

## 3. The only concept we own on a switch node: the decision maker

The system knows exactly one thing about a branching node — **who chooses.**

| Decided by | Behavior |
|------------|----------|
| LLM        | A node with 2+ labelled outgoing edges; the model picks one label |
| Human      | `run: human.checkpoint` interrupts, and a person picks one of the wired labels |

## 4. Flow grammar

- Whether a node branches is determined by **the number of labelled outgoing edges, not names**. No name whitelists.
- A node has one outgoing edge by default. Multiple edges only when branching.
- A node with 2+ plain incoming edges needs `join: all` or `join: any`.
- Cycles get a `loop.guard` inserted automatically if the author does not write one.

## 5. Roadmap

Each phase ships on its own and is useful before the next one starts.

| Phase | Scope | Status |
|---|---|---|
| 1 | CLI (`check`/`run`/`resume`/`show`) + Claude Code skill, SQLite checkpointer, `join`/`temperature`/`max_tokens` in YAML | ✅ done |
| 2 | `agentforge replay` — re-run from the first changed node, reusing earlier outputs | ✅ done |
| 3 | Honest cost records (no silent $0 for unpriced models) ✅, `eval:` in `arch.yaml`, comparison reports | 🟡 in progress |
| 4 | `run: agent` nodes wrapping mini-swe-agent (bash-only tools, per-run git worktree, Tavily search) | ⬜ |
| 5 | Per-node sandbox with bwrap (`network`/`files`/`secrets`/`limits` per node) | ⬜ |

## 6. Known stale code (to fix)

These still use fixed branch vocabulary, against §2:

- `server/nodes/policy.py` — `ReviewBranch = Literal["accept","refine","clarify"]`
- `server/nodes/review.py` — the prompt is written in that vocabulary (still used by `graphs/treatment.py`)
- `server/harness.py` — metrics count branch names (`refine_rate`/`clarify_rate`)

`graphs/baseline.py`/`graphs/treatment.py` are the pre-YAML fixed GSM8K graphs, kept for the
benchmark harness.

## 7. Documents

- Tracked: `README.md` (users), `CLAUDE.md` (layout and setup), `AGENTS.md` (coding rules),
  `backend-architecture.md` (how the backend works today), `skills/agentforge/SKILL.md` (the skill).
- `docs/` and `refer_data/` are local and not in the repository. Design notes in `docs/` are
  working material, not the current design. `refer_data/docs/**` are early planning documents,
  read-only; anything conflicting with §2–4 is void.
- Git handles backups. Do not keep separate copies of documents.
