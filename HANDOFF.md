# Work Handoff

> Incoming agent: read the repository instructions and inspect the current worktree before acting. Repository state and fresh command output override this document if they differ.

## Snapshot

- **Updated:** 2026-08-11T18:01:26Z
- **Status:** complete — Loop node (`loop.guard`) merged to `main`; its priority `io.input` follow-up and documentation reconciliation are committed too. Only polish-level follow-ups remain (see Remaining Work).
- **Repository:** AgentForge
- **Branch / commit:** `main` / `ec4b02b`
- **Worktree:** clean except for pre-existing unrelated items: modified `start.sh` (user's own port/LAN-exposure change, unrelated to this work); untracked `.agents/`, `.opencode/`, `agentforge`. Do not stage, revert, or delete those without user direction. `ROADMAP.md` was updated on disk during the prior session but is intentionally git-ignored, so it carries no tracked diff and needs an explicit force-add decision if it should ever be committed.

## Objective

Replace the `LoopPolicy` "sidecar" loop-control model (2026-08-06 design: a separate `Architecture.loopPolicies` array referencing edges by id, with the compiler splicing in a synthetic `__loop_guard__<id>` node) with a first-class `loop.guard` **canvas node** that the user draws directly: one input (`Feedback`), two outputs (`Loop back` / `Exit`), and a 5-axis guard config (`maxIterations`/`maxTokens`/`maxCostUsd`/`maxDurationSec`/stuck). The sidecar version was merged on 2026-08-06 having never been executed once — this rework's explicit goal was to not repeat that.

Completion criteria (from the design spec, `docs/superpowers/specs/2026-08-07-loop-node-design.md`):

- `loop.guard` is an ordinary `BUILTIN_MANIFESTS` entry (backend + frontend registry), rendered by the existing generic node renderer (no custom UI component).
- `compile_graph` treats it as a peer of `human.checkpoint` — self-routes via `Command(goto=...)`, skipped in the plain-edge wiring loop.
- Any cycle drawn on the canvas without a `loop.guard` node in it fails to compile (`ValueError`), replacing the old sidecar's edge-reference validation with a structural, graph-level check.
- The pure guard-evaluation core (`server/nodes/loop_guard.py`) and its tests stay untouched — it was already decoupled from the sidecar's wiring, so a full data-model replacement should not need to touch it.
- The system actually runs: a permanent WS integration test, a live GSM8K benchmark, and a live WebSocket run of the starter graph with `loop.guard` in it, all with real evidence (not just green unit tests).

All of the above is met and merged. See Remaining Work for what's intentionally left open.

## Current State

A prior session executed the full spec → plan → subagent-driven-development → merge cycle for the redesign, then wrote this handoff. This session resumed from that handoff, reconciled it against the live worktree (git status, full backend/frontend test+lint+build suites all reproduced the recorded results exactly), and committed the local `io.input` fix + doc reconciliation as `ec4b02b`. Sequence (prior session unless noted):

1. Brainstormed and wrote `docs/superpowers/specs/2026-08-07-loop-node-design.md`, which explicitly **supersedes** `docs/superpowers/specs/2026-08-06-loop-policy-design.md` (that file and its plan now carry a superseded banner pointing here).
2. Had an Opus subagent write `docs/superpowers/plans/2026-08-07-loop-node-implementation.md` (11 tasks), which independently re-verified the spec against the actual 8/6 code and caught 4 real bugs in the spec's own snippets before they could ship (documented in the plan's "Deliberate deviations from the spec" section).
3. Ran the plan via `superpowers:subagent-driven-development` in an isolated worktree (`.worktrees/loop-node-implementation`, now removed) on branch `loop-node-implementation` (now deleted, merged). Every task got a fresh implementer + independent task-scoped reviewer; the final whole-branch review ran on Opus.
4. Fast-forward merged to `main` (`0bf181c`). Worktree and branch cleaned up.

Present state of `main`:

- `loop.guard` manifest lives in `server/manifests.py` (between `review.intent` and `human.checkpoint`) and `ui/src/registry/builtinManifests.ts`. Port ids `in`/`loopBack`/`exit`; config keys `kind, maxIterations, maxTokens, maxCostUsd, maxDurationSec, stuckWindow, stuckThreshold, onExhaustion`, in that order.
- `server/graphs/compile.py` registers `loop.guard` as its own node-type branch inside `compile_graph`'s main loop (self-routes, skipped in plain-edge wiring — same pattern as `human.checkpoint`). Supporting pure functions, all in this file: `_loop_policy_from_config` (flat node config → the nested dict `evaluate_loop_guard` expects), `_derive_loop_members` (graph-reachability-based budget attribution, replacing the sidecar's user-declared `memberNodeIds`), `_tarjan_scc` + `_validate_gated_cycles` (ported from the frontend's now-deleted `loopCandidates.ts`; pruned of guard-node outgoing edges before the SCC search — see the Important fix below), `_handle_targets` (sourceHandle→target indexing, shared by `human.checkpoint`/`loop.guard`/`review.intent`).
- `server/nodes/loop_guard.py` and `server/tests/test_loop_guard.py` are **byte-for-byte unchanged** from before this session — verified via `git diff` across the whole branch. The guard-evaluation core was already decoupled from the sidecar wiring, and that decoupling held.
- The old `LoopPolicy` Zod schema, `ArchitectureSchema.loopPolicies`, and `useGraphStore`'s `loopPolicies` state are **deleted** (`ui/src/types/graph.ts`, `ui/src/stores/useGraphStore.ts`). `LOOP_POLICY_KINDS`/`LOOP_POLICY_EXHAUSTION_ACTIONS` (plain string-array constants) survive — they feed the `loop.guard` manifest's `kind`/`onExhaustion` select options.
- The entire "Loop Scope Lens" UI feature — SCC-based cycle detection + Tier 1/2/3 classification + collapse/expand UI, ~2,500 lines across `ui/src/canvas/loops/`, `LoopScopeNode.tsx`, `LoopAnchor.tsx`, `LoopControlPanel.tsx`, `LoopCandidateInspector.tsx`, `LoopScopeInspector.tsx` and their tests — is **deleted**. Most of it was already orphaned dead code from an earlier UI rewrite (08-05) before this session started; the rest was deleted by user decision (Lens superseded by the drawable node).
- `ui/src/app/starterArchitecture.ts` now has a `loop_guard` node gating the `Reasoning → Review → (refine) → Reasoning` loop (node id `loop_guard`, edges `e9`/`e10`) — required, since an ungated cycle no longer compiles.
- `loopRuntime.loopPolicyId` was renamed to `loopRuntime.loopNodeId` on the wire (`server/graphs/compile.py`, `ui/src/types/events.ts`) — it's now the real canvas node id, so the frontend can consume guard events exactly like any other node's events (no more "Unknown node" special-casing for a synthetic id).
- `server/tests/test_ws_starter_graph.py` (new) is a permanent WS integration test mirroring the starter graph, mocked at the LLM boundary only. It passed on the first real run, and Task 11 additionally ran a live GSM8K benchmark (`server/data/benchmark-20260808T085907Z.json`) and a live `/ws/run` execution that actually hit `loop.guard` (verified via `server/workspace/<uuid>/` artifacts inside the isolated worktree at the time — those specific run directories no longer exist since removing the worktree after merge deleted them along with it; the benchmark JSON is the surviving committed evidence).
- The priority `io.input` follow-up is fixed and committed (`ec4b02b`, this session): `_make_passthrough_node` now preserves a non-empty submitted `state.task`; `config.sample` remains a fallback only for an empty submission. The `node_end` event reports the effective task. Unit and full-WebSocket regression tests submit a task distinct from the canvas sample and verify every mocked LLM invocation and the input event see the submitted value.
- Full design record: `docs/superpowers/specs/2026-08-07-loop-node-design.md`. Full implementation record: `docs/superpowers/plans/2026-08-07-loop-node-implementation.md`. The 8/6 spec/plan are kept for history with superseded banners, not deleted.

## Decisions and Rationale

| Decision | Rationale | Alternatives / consequences |
| --- | --- | --- |
| `loop.guard` as an ordinary node vs. a sidecar or a subgraph container | A node with real edges makes edge-reference integrity structural (React Flow can't draw an edge to a nonexistent port), removes the v1 whitelist restricting which node types could feed a loop, and matches ComfyUI's flow-visibility philosophy. A container (subgraph) was rejected — LangGraph subgraph nesting would have forced a large restructure of `compile_graph`'s flat `StateGraph` for no benefit `loop.guard`-as-node doesn't already get. | Sidecar (rejected, this session's whole reason for existing); subgraph container (rejected, disproportionate rework). |
| Freeze `server/nodes/loop_guard.py`/`test_loop_guard.py` for the whole plan | The 8/6 design had already decoupled pure guard-evaluation logic from wiring; re-verifying that decoupling by never touching those files during a full data-model swap is itself the proof it was a good boundary. | Held for all 11 tasks — confirmed via `git diff` at merge. |
| `_derive_loop_members` (graph reachability) replaces sidecar's declared `memberNodeIds` | A declared list can drift from the actual graph; reachability from the guard's `loopBack` target back to the guard itself is always correct by construction, and needs no validation. | None — this is strictly simpler than what it replaced. |
| Prune each `loop.guard` node's outgoing edges before running the Tarjan SCC cycle check | Found in final whole-branch review: Tarjan merges *all* cycles sharing a single node into one SCC, so an ungated cycle sharing just one node with a gated cycle was silently accepted by the naive `component ∩ loop_node_ids` check. Pruning guard outgoing edges first means any surviving size-≥2 component is, by construction, untouched by any guard. | Fixed before merge (`server/graphs/compile.py:_validate_gated_cycles`), with a regression test encoding exactly this adversarial shape. |
| Inspector's numeric guard-config fields must render empty (not `0`) when unset, and clearing a field deletes the key rather than writing `0` | Found in the same final review: the old behavior made every fresh `loop.guard` node visually show all five budget axes as already-tripped-at-zero, and gave users no way to express "unlimited" once they'd touched a field. | Fixed before merge (`ui/src/panels/Inspector.tsx`, `ui/src/stores/useGraphStore.ts`'s `updateNodeConfig`). |

## Completed Work

- `docs/superpowers/specs/2026-08-07-loop-node-design.md` — design spec, supersedes the 8/6 sidecar spec.
- `docs/superpowers/plans/2026-08-07-loop-node-implementation.md` — 11-task implementation plan with exact code, self-reviewed against the actual codebase before execution.
- `server/manifests.py`, `ui/src/registry/builtinManifests.ts`, `ui/src/types/manifest.ts` (`RUNTIMES` += `'loop_guard'`) — the `loop.guard` node type.
- `server/graphs/compile.py` — `loop.guard` node-type branch in `compile_graph`; `_loop_policy_from_config`, `_derive_loop_members`, `_tarjan_scc`, `_validate_gated_cycles`, `_handle_targets`; deletion of `_prepare_loop_policies` and the sidecar's `edge_target_override` mechanism.
- `server/graphs/compile.py` / `ui/src/types/events.ts` — `loopRuntime.loopPolicyId` → `loopNodeId`; dropped the unused `progress` field; added a comment on which `LOOP_RUNTIME_EXIT_REASONS` values are actually reachable.
- `ui/src/types/graph.ts`, `ui/src/stores/useGraphStore.ts` — deleted `LoopPolicySchema`/`LoopPolicyGuardSchema`/`ArchitectureSchema.loopPolicies` and the store's round-trip; kept `LOOP_POLICY_KINDS`/`LOOP_POLICY_EXHAUSTION_ACTIONS`.
- Deleted (dead + superseded): `ui/src/canvas/loops/` (whole directory, 8 files), `ui/src/canvas/nodes/{LoopScopeNode,LoopAnchor}.tsx`, `ui/src/canvas/LoopControlPanel.tsx`, `ui/src/panels/{LoopScopeInspector,LoopCandidateInspector}.tsx`, plus their tests and the now-dead six-member state slice in `ui/src/stores/useUiStore.ts`. Cleaned up call sites in `Canvas.tsx`, `Inspector.tsx`, `AgentNode.tsx`.
- `ui/src/app/starterArchitecture.ts` — added the `loop_guard` node gating the refine loop.
- `ui/src/panels/Inspector.tsx` — numeric guard-config fields render empty when unset and clear-to-unset correctly (final-review fix).
- New tests: `server/tests/test_ws_starter_graph.py` (WS integration, 2 tests), `ui/src/__tests__/{loopGuardManifest,starterArchitecture,Inspector}.test.{ts,tsx}`; extensive rewrites in `server/tests/test_compile.py` (sidecar tests → node-based equivalents, SCC tests, member-derivation tests).
- `server/data/benchmark-20260808T085907Z.json` — committed evidence of the live GSM8K run.
- 19 commits on `main` from `071fb44` (manifest) through `ec4b02b` (`io.input` precedence fix); full list via `git log --oneline 05488b3..ec4b02b`.
- `ec4b02b` (this session): `server/graphs/compile.py`, `server/tests/test_compile.py`, `server/tests/test_ws_starter_graph.py`, and `backend-architecture.md` — submitted task precedence, regressions, and documented fallback contract.
- Documentation reconciliation (partly committed in `ec4b02b`, partly local): `backend-architecture.md` now points to the existing compile and WebSocket tests (committed); `ROADMAP.md` records `loop.guard` completion and precisely scopes ungated-cycle rejection to components of two or more nodes, but stays uncommitted since it's git-ignored; the loop design spec metadata now records implementation and verification as complete (committed).

## Evidence and Verification

| Command or evidence | Result | Notes |
| --- | --- | --- |
| `server/.venv/bin/python -m pytest -q` (post-merge, on `main`) | 144 passed | Includes `test_loop_guard.py`'s original tests, unchanged, still passing. |
| `npm run test` in `ui/` (post-merge, on `main`) | 67 passed, 14 files | |
| `npm run build` in `ui/` (post-merge, on `main`) | Passed | `tsc -b` + Vite build; only the pre-existing >500 kB chunk-size warning remains. |
| `server/.venv/bin/ruff check .` (post-merge, on `main`) | All checks passed | |
| Live GSM8K benchmark (`scripts/run_benchmark.py`) against `gemini-3.1-flash-lite` | Passed | Result: `server/data/benchmark-20260808T085907Z.json`. Note: this benchmark builds via `graphs/baseline.py`/`graphs/treatment.py`, **not** `compile_graph` — it proves live-model health, not `loop.guard` specifically. |
| Live `/ws/run` execution of the starter graph (with `loop.guard`) | Passed | Produced a real `server/workspace/<uuid>/` run with guard events inside the isolated worktree at the time; removing that worktree after merge (standard cleanup) took the run directory with it — the benchmark JSON above is the surviving artifact. |
| `git diff` across the whole branch for `server/nodes/loop_guard.py`, `server/tests/test_loop_guard.py`, `server/state.py`, `server/nodes/llm_step.py`, `server/nodes/review.py` | Empty | Frozen-file constraint held for all 11 tasks + the final fix wave. |
| Repo-wide grep for `LoopPolicy\|loopPolicies\|LoopScope\|loopScope\|LoopAnchor\|loopCandidate\|LoopControlPanel` under `ui/src` | No matches | Confirms the deletion is complete, not partial. A deliberate negative-payload test still references the old field name via the literal string `loopPolicyId` (`ui/src/__tests__/events.schema.test.ts:80`) — not covered by this alternation, so it doesn't show up here, but it's the intended remaining reference and asserts old payloads are rejected. |
| `server/.venv/bin/python -m pytest -q server/tests/test_compile.py server/tests/test_ws_starter_graph.py` | 45 passed | New task-precedence unit and WebSocket regression coverage included. |
| `server/.venv/bin/python -m pytest -q` | 145 passed | Post-`io.input`-fix full backend suite; only the existing Starlette/httpx deprecation warning remains. |
| `server/.venv/bin/ruff check server` → `server/.venv/bin/ruff format server` | Passed; 41 files unchanged | Post-`io.input`-fix lint and format verification. |
| `git diff --check` plus current ROADMAP/source review | Passed | Documentation update reconciled with `_validate_gated_cycles` behavior: only SCCs of size ≥2 are rejected after guard outgoing edges are pruned. |
| Browser/manual visual verification of the canvas | Not run | This environment lacks a working Chromium runtime (no `libatk-1.0.so.0`, no passwordless sudo) — unchanged from before this session. |
| `server/.venv/bin/python -m pytest -q` / `ruff check .` / `ruff format --check .` / `npm run test -- --run` / `npm run build` (this session, pre-commit, reconciling this handoff against the live worktree) | 145 passed; all checks passed; 41 files already formatted; 67 passed, 14 files; build passed (only pre-existing >500 kB chunk warning) | Confirms the handoff's prior evidence rows still reproduce exactly before committing `ec4b02b`. |

## Remaining Work

1. **Loop node config-form polish** (explicitly deferred, not a defect): no `kind`-specific guard presets (e.g. `humanReview` still shows `stuckWindow`/`stuckThreshold` even though stuck detection has nothing to key off for that kind), and the `onExhaustion: 'escalate'` option is currently behaviorally identical to `'exit'` (same routing, same event) — the UI offers a choice with no observable difference yet.
2. **Minor code-quality items**, all deferred by design during final review (see `docs/superpowers/specs/2026-08-07-loop-node-design.md`'s companion plan and the merge commit history for exact file:line — the SDD workspace ledger that tracked these in detail was deleted after the branch merged, per the process's own cleanup step):
   - `_tarjan_scc`'s recursive implementation has no depth cap (~1000-node chain before Python's default recursion limit trips); fine for hand-drawn canvas graphs, would need converting to an explicit-stack iterative form if this is ever fed a programmatically generated large graph.
   - A `_loop_guard_targets` extraction from `compile_graph`'s `loop.guard` branch (currently ~34 inline lines vs. 3-8 for sibling branches) was suggested for readability parity, not correctness — deferred to avoid last-minute refactor risk right before merge.
3. **Loop Control UI settings surface** (carried over from the 8/6-era handoff, now updated for the new node model): there's still no dedicated polish pass on the `loop.guard` node's Inspector config beyond the empty/clear-to-unset fix — e.g. grouping the five budget axes visually, or showing a live iteration/budget readout on the node itself during a run (the event data exists on the wire now; nothing consumes it into a nicer visual yet beyond the generic Inspector fields).

## Blockers and Open Questions

- **Manual visual verification:** blocked by unavailable browser runtime in this sandbox, not by a known code failure.
- None of the `loop.guard` work itself is blocked — it is merged, tested, and green on `main`.

## Working Context

- **Key files / symbols:** `server/graphs/compile.py:compile_graph,_loop_policy_from_config,_derive_loop_members,_tarjan_scc,_validate_gated_cycles,_handle_targets`; `server/nodes/loop_guard.py:evaluate_loop_guard,next_runtime` (frozen, do not modify without good reason); `server/manifests.py` (search `"type": "loop.guard"`); `ui/src/registry/builtinManifests.ts` (search `'loop.guard'`); `ui/src/app/starterArchitecture.ts:loop_guard` node + `e9`/`e10` edges; `ui/src/panels/Inspector.tsx` (numeric config-field rendering); `server/tests/test_ws_starter_graph.py`.
- **Requirements / instructions:** read `AGENTS.md` and `CLAUDE.md`. Frontend changes must pass `npm run lint`, `npm run test`, `npm run build` (`tsc -b` catches errors `tsc --noEmit` misses, per `CLAUDE.local.md`). Backend changes must pass `.venv/bin/ruff check .`, `.venv/bin/ruff format .`, `.venv/bin/python -m pytest -q` (never the venv's bare `pytest` binary — broken shebang). Fields shared between backend and frontend stay camelCase on both sides, no snake_case leaking.
- **Environment / setup:** project root is this directory; frontend deps in `ui/node_modules`; backend venv at `server/.venv`. Default execution model is `gemini-3.1-flash-lite` (Google) — `config.yaml:models.default` — so `GOOGLE_API_KEY` in `server/.env` is what live verification depends on, not the Anthropic key.
- **Scope guardrails / non-goals:** do not modify `server/nodes/loop_guard.py` or `server/tests/test_loop_guard.py` without a deliberate reason to break that boundary — the whole design rests on that file being wiring-agnostic. Do not change user-owned `start.sh`, `.agents/`, `.opencode/`, or `agentforge` without explicit direction. `kind: 'retry'` and kind-specific guard presets are explicitly out of scope for v1. Self-loop cycles (a node feeding directly back to itself) are deliberately not required to carry a `loop.guard` — only SCCs of size ≥2 are gated.

## Resume Instructions

1. Read `AGENTS.md`, `CLAUDE.md`, `CLAUDE.local.md`, this `HANDOFF.md`, and `docs/superpowers/specs/2026-08-07-loop-node-design.md`.
2. Reconcile this snapshot with `git status --short`, `git log --oneline -5`, and current source — current files and fresh test output override this document.
3. Start with one of the three Remaining Work items — all are polish-level, none are blocked. Item 1 (`loop.guard` config-form polish: kind-specific presets, `onExhaustion: 'escalate'` vs `'exit'`) is the most user-visible. Use CodeGraph (`.codegraph/` exists) before grepping/reading files by hand.
4. After material progress, update this handoff with fresh evidence.
