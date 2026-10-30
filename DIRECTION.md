# Current direction (source of truth)

> Last updated: 2026-09-02. **This document takes precedence over every other design document.**
> If another document conflicts with this one, that document is out of date.

> **2026-09-02 text-first switch**: the authoring model assumed by §1 and §4 below —
> "build by drawing on a node canvas (React Flow)" — has been retired. Authoring is now
> `server/arch/*.yaml` text, and the diagram (mermaid) is a read-only artifact generated
> automatically from that text. Detailed design:
> `docs/superpowers/specs/2026-09-02-text-first-architecture-design.md`.
> The principles in §2 and §3 (unfixed roles, decision maker) remain valid — a `custom.node`
> instance defines its name, prompt, and inputs/outputs, and branching is still determined by
> the number of labels, not by names. The canvas, Inspector, and node palette themselves have
> been deleted (see `.superpowers/sdd/2026-09-02-text-first-architecture/task-7-report.md`).

## 1. What we are building (as of 2026-08-28 — written before the canvas was retired, see banner above)

**A canvas for drawing LLM agent architectures and running/testing them in place.**
It is not a static diagramming tool (cf. archify), nor a general-purpose system architecture tool.
What you draw is an LLM agent pipeline, and what you draw runs as-is.

Now: **build it as text (`arch.yaml`) and run/test it in place.** The diagram is not the
authoring medium; it is a read-only by-product showing what the text produced.

## 2. We do not fix node roles

- We do **not hard-code roles** such as "reviewer" or "planner" into node types. The user
  defines roles through the name, system prompt, and input/output ports (`custom.node`,
  edited in the Inspector).
- Branch names (`accept`/`refine`/`clarify`, `approve`/`revise`/`reject`) are **examples,
  not a contract.** Users must be able to create branches with any count and any names.
- What we provide is **the switch as a mechanism**, not the meaning of the switch.

## 3. The only concept we own on a switch node: the decision maker

The system knows exactly one thing about a branching node — **who chooses.**

| `decidedBy` | Behavior |
|-------------|----------|
| `llm`       | The LLM picks one of the declared branch names |
| `human`     | Interrupt, and a human picks via branch buttons |

`review.intent` (LLM decision) and `human.checkpoint` (human decision) converge into **two
settings of the same node**. We do not keep them as separate types with separate code paths.

## 4. Diagram grammar (before 2026-09-02: canvas visual grammar — now applies to the auto-generated mermaid diagram)

- Whether a node branches is determined by **the number of output ports (labels), not names**. No name whitelists.
- A node has one outgoing edge by default. Multiple edges only when branching.
- The decision maker is either the LLM or a human (`custom.node` is LLM-decided, `human.checkpoint` is human-decided).

The part of this section that said "the canvas colors edges directly by branch index" is void
now that the canvas is gone — mermaid draws the diagram, and mermaid/the browser decides colors.
There are no canvas-only UI devices such as node badges either.

## 5. Known stale code (to fix)

> 2026-09-02: the canvas-related items (struck through below) disappeared along with the
> canvas itself — resolved as "no longer exists" rather than "to fix". The rest (hard-coded
> branch names) is still a valid to-do — `treatment.py`/`baseline.py`/`harness.py` were not
> touched in this switch.

- ~~`ui/src/canvas/edges/edgePresentation.ts` — branch name whitelist~~ (file deleted)
- `server/nodes/policy.py` — `ReviewBranch = Literal["accept","refine","clarify"]`
- ~~`server/manifests.py` / `ui/src/registry/builtinManifests.ts` — the three fixed output
  ports of `review.intent`~~ (both deleted — `review.intent` from `manifests.py`, and the
  `ui/src/registry/builtinManifests.ts` file itself)
- `server/nodes/review.py` — the prompt is written in the vocabulary above (still used by treatment.py)
- `server/harness.py` — metrics count branch names (`refine_rate`/`clarify_rate`)
- ~~`ui/src/canvas/edges/AgentEdge.tsx` — edges were drawn to the target's center so the
  arrowhead was buried inside the node circle (a real bug: direction was invisible)~~ (file deleted)

## 6. Document handling rules (four banners)

The banner on the first line of each document tells you how to read it.

| Banner | Applies to | How to read |
|---|---|---|
| 📄 **Completed work log** | `docs/superpowers/plans/*`, `work/**` | A log of work already done. Do not treat as design |
| 📚 **Stale design / research notes** | `docs/superpowers/specs/*`, `POLICY_RESEARCH.md` | Only when looking for the reasoning behind a past decision |
| 🔁 **Superseded by the 2026-09-02 text-first switch** | `specs/2026-08-16-freeform-connections-node-templates-design.md`, `specs/2026-08-22-loop-reentry-node-design.md` | Void. The canvas/node palette premise is gone — the follow-up design in its place is `specs/2026-09-02-text-first-architecture-design.md` |
| ✅ **Currently in progress** | `specs/2026-09-02-text-first-architecture-design.md`, `plans/2026-09-02-text-first-architecture.md` | Valid. These take precedence for anything about arch.yaml authoring and mermaid diagrams |
| No banner | `CLAUDE.md`, `ROADMAP.md`, `backend-architecture.md`, `POLICY_REDESIGN.md` | Current documents. These still take precedence for the target design |

- `POLICY_REDESIGN.md` §0 has a table of what was invalidated.
- `refer_data/docs/**` — early planning documents, read-only. Anything conflicting with §2–4 is void.
- Git handles backups. Do not keep separate copies of documents.
