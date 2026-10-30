# Agentforge — Backend Design & Frontend Integration

> Status: Living doc — **a description of the current code**, not the target design.
> [DIRECTION.md](./DIRECTION.md) takes precedence for the target design (node roles and branch names are defined by the user).
> First written: 2026-06-26 · Full revision: 2026-06-30 · Partial revision: 2026-07-03 (reflects v0.3 compile_graph · workspace · review/policy redesign)
> Related: [CLAUDE.md](./CLAUDE.md) · [AGENTS.md](./AGENTS.md) · [ROADMAP.md](./ROADMAP.md) · [ui-architecture.md](./refer_data/docs/ui-architecture.md)

This document describes **what the FastAPI backend implements and how it integrates with the frontend**.
The frontend code (`ui/src/transport/`, `ui/src/types/`) defines the contract, and the backend fulfills it.

> 📌 **Revision note**: the 2026-06-26 draft of this document assumed an abstract `NodeBase` class + `NodeRegistry` +
> a topological-sort `ExecutionEngine`, and deferred LangGraph as a "later upgrade". **The actual implementation
> skipped that stage and adopted LangGraph `StateGraph` from v0.1.** This revision was rewritten against the actual
> code (`server/`). If you need the old draft, see the git history.

---

## 0. Core integration principles

The backend connects to the frontend by fulfilling just two contracts.

1. **REST `GET /api/nodes`** — returns the list of node manifests (populates the node palette)
2. **WebSocket `ws://…/ws/run`** — streams execution events + receives control messages (run / resume / reconnect)

Additional contracts: `GET /api/models` (model dropdown), `GET|POST /api/architectures` (save/load).

Key rule: **types are unified in camelCase**. Payloads the backend sends over WS/REST are serialized in camelCase,
as in `ExecutionEvent.to_frontend()`, and map 1:1 to the frontend Zod schemas (`ui/src/types/`).
There is no snake_case ↔ camelCase conversion layer (AGENTS.md §4).

---

## 1. Tech stack

| Area | Used |
|------|------|
| Web framework | FastAPI + uvicorn |
| Execution engine | **LangGraph** (`StateGraph`, `MemorySaver`, `interrupt`/`Command`) |
| LLM adapters | LangChain (`langchain-core`, `langchain-anthropic`, `langchain-openai`, `langchain-google-genai`) |
| Types/validation | Pydantic v2 (LLM structured output schemas) |
| Config | PyYAML (`config.yaml`) + python-dotenv (`.env` API keys) |
| Packaging | `uv` (Python 3.12, `server/.venv`) |

---

## 2. Project structure (actual)

```
agentforge/
├── config.yaml              # Central config: server, model list, run parameters, UI
├── server/
│   ├── main.py              # FastAPI app, REST, WebSocket (ws_run), dispatch_graph
│   ├── manifests.py         # BUILTIN_MANIFESTS (list of node manifest dicts)
│   ├── models.py            # LLM output schemas (PlanOut/ReasonOut/Criterion/CriterionVerdict/ReviewDelta) + build_model factory
│   ├── state.py             # AgentState (TypedDict) + initial_state
│   ├── events.py            # ExecutionEvent + make_event/make_error_event + WS/List emitter
│   ├── logging_config.py    # setup_logging() / logger
│   ├── harness.py           # Benchmark harness (run_dataset + gsm8k_grader + Report)
│   ├── workspace.py         # Run artifacts — saves/reads node_end output as workspace/<run_id>/*.md
│   ├── config.py            # Loads config.yaml + .env
│   ├── nodes/               # Node helpers called by graphs (not a NodeRegistry)
│   │   ├── __init__.py      # Empty package marker
│   │   ├── llm_step.py      # run_llm_step (structured-output LLM call)
│   │   ├── checkpoint.py    # make_human_checkpoint (interrupt-based)
│   │   ├── review.py        # make_review — intent×criteria review (produces ReviewDelta)
│   │   └── policy.py        # compute_review_branch / make_route_review (pure routing functions)
│   ├── graphs/              # LangGraph StateGraph definitions (= the actual execution engine)
│   │   ├── baseline.py      # build_baseline
│   │   ├── treatment.py     # build_treatment
│   │   └── compile.py       # compile_graph — dynamically compiles a canvas Architecture (dict) (v0.3)
│   ├── architectures/       # Storage for POST /api/architectures (JSON files)
│   ├── workspace/           # Per-run node output .md files (<run_id>/<seq>-<node_id>.md)
│   └── tests/               # pytest (35 tests)
└── ui/                      # Frontend (separate document)
```

> The draft's `backend/`, `nodes/base.py`, and `execution/engine.py` do not actually exist. Execution logic lives
> in the `StateGraph` builders under `graphs/`.

---

## 3. Type contract — frontend Zod ↔ backend Pydantic/dict

### 3.1 NodeManifest

The definition of a node *type*. The backend holds these not as Pydantic models but as **a list of dicts**
(`BUILTIN_MANIFESTS` in `manifests.py`), and `GET /api/nodes` returns them as-is. The frontend parses them with
`NodeManifestSchema` (Zod) in `ui/src/types/manifest.ts`.
There are 7 builtins: `io.input` / `io.output` / `model.binding` / `planning.decompose` / `reasoning.cot` / `review.intent` / `human.checkpoint`.

Shape of a single manifest:

```python
{
    "type": "reasoning.cot",          # Unique type id
    "runtime": "llm_step",            # Execution mapping hint (llm_step/policy/checkpoint/io/model)
    "category": "cognitive",          # Palette category (cognitive/memory/model/tool/policy/human/io)
    "label": "Reasoning",
    "description": "Chain-of-thought reasoning.",
    "maxModelSlots": 2,               # When set, inline model slot UI instead of a model input port
    "inputs":  [{"id": "task", "label": "Task", "dataType": "text", "required": True}, ...],
    "outputs": [{"id": "answer", "label": "Answer", "dataType": "text"}, ...],
    "config":  [{"key": "style", "label": "Style", "type": "select", "options": [...]}],
    "defaults": {"systemPrompt": "...", "outputSchema": {"answer": "string", "confidence": "number"}},
}
```

> ⚠️ Contract change warning: when adding a manifest field, update the Zod schema in the frontend `manifest.ts` **at the same time**.
> Recent change: the external `model` input port was replaced with `maxModelSlots` inline slots (`ModelSlotSchema`).

### 3.2 Architecture (the graph the frontend sends in a `run` message)

A serialization of the canvas nodes/edges. Built by the frontend's `useGraphStore.toArchitecture(name)`.

```jsonc
{
  "version": "0.1",
  "metadata": { "name": "gsm8k-treatment", "createdAt": "..." },
  "nodes": [
    { "id": "reasoning", "type": "reasoning.cot", "position": {"x":300,"y":360}, "config": {} }
  ],
  "edges": [
    { "id": "e4", "source": "reasoning", "sourceHandle": "answer",
      "target": "review_policy", "targetHandle": "answer" }
  ]
}
```

> If `architecture.metadata.name` is a fixed name (`gsm8k-baseline`/`gsm8k-treatment`), the backend dispatches to
> the fixed graph; otherwise it compiles `nodes`/`edges` directly into a `StateGraph` with `compile_graph` (§7.1, §12).

### 3.3 ExecutionEvent (backend → frontend, WS streaming)

`ExecutionEvent` in `events.py`. `to_frontend()` builds a camelCase dict that goes out over WS.
1:1 with `ExecutionEventSchema` in the frontend `ui/src/types/events.ts`.

| Field (camelCase) | Meaning |
|-------------------|---------|
| `eventType` | `node_start` / `node_end` / `error` / `interrupt` / `decision_record`, etc. |
| `runId`, `nodeId`, `timestamp` | Always included |
| `durationMs` | Node execution time (optional) |
| `output` | Node output — shown as JSON in the Inspector (serializable values only) |
| `tokenUsage` | `{total_tokens, ...}` (optional) |
| `policyDecision` | `{activated: bool, reason: str}` — Policy node |
| `error` | `{type, detail}` — on failure (see node error standard) |
| `message` | Free text |

Construction helpers:
- `make_event(run_id, node_id, event_type, **kwargs)` — general event
- `make_error_event(run_id, node_id, exc)` — `eventType="error"` + structured `error={type, detail}`

### 3.4 WebSocket protocol

**Frontend → backend** (`kind`):

```jsonc
// Start a run
{ "kind": "run", "architecture": {...}, "input": { "task": "...", "task_tags": [] },
  "model": { "provider": "anthropic", "model": "claude-haiku-4-5-20251001", "temperature": 0 } }

// Resume a Human Checkpoint
{ "kind": "resume", "runId": "...", "decision": { "action": "approve|revise|reject", "edits": {}, "reason": "" } }

// Reconnect (request a snapshot of accumulated events)
{ "kind": "reconnect", "runId": "..." }
```

**Backend → frontend** (`kind`):

```jsonc
{ "kind": "run_started", "runId": "..." }
{ "kind": "event", "event": { /* ExecutionEvent.to_frontend() */ } }
{ "kind": "run_complete", "runId": "...", "result": { "answer": "...", "reviewDelta": {...}, "reviewBranch": "accept" } }
{ "kind": "error", "runId": "...", "message": "..." }
{ "kind": "state", "runId": "...", "snapshot": [ /* array of accumulated events */ ] }   // reconnect response
```

The frontend `TransportContext.tsx` receives these messages and applies them to `useExecutionStore`.

---

## 4. REST API (`server/main.py`)

| Endpoint | Description |
|----------|-------------|
| `GET /api/nodes` | Returns `BUILTIN_MANIFESTS` (node palette) |
| `GET /api/models` | `enabled` models from `models.list` in `config.yaml`. Shows whether each provider's API key is present via the `available` field |
| `GET /api/architectures` | All of `server/architectures/*.json` |
| `POST /api/architectures` | Saves an architecture JSON (generates a uuid if `id` is missing) |
| `GET /api/architectures/{id}` | Fetch one (404 if missing) |
| `GET /api/runs/{run_id}/files` | Workspace file list — `[{name, nodeId, sizeBytes}]` (camelCase) |
| `GET /api/runs/{run_id}/files/{name}` | Single file content — `{name, content}`. Guards against path traversal, 404 if missing |

A single `GET /api/models` response entry:

```jsonc
{ "id": "claude-haiku-4-5-20251001", "provider": "anthropic", "label": "Claude Haiku 4.5",
  "description": "...", "available": true, "temperature": 0.0, "maxTokens": 4096 }
```

---

## 5. WebSocket endpoint — the core of the integration (`main.py: ws_run`)

### 5.1 Flow

```
accept
  └─ while True: receive_text → json
       ├─ kind="run":       create run_id → run_started → dispatch_graph → graph.ainvoke → run_complete
       ├─ kind="resume":    look up active_runs[run_id] → graph.ainvoke(Command(resume=decision))
       └─ kind="reconnect": snapshot run_history[run_id] → state
  (ends on WebSocketDisconnect)
```

State kept (in process memory):
- `run_history: dict[run_id, list[ExecutionEvent]]` — for resending on reconnect
- `active_runs: dict[run_id, CompiledGraph]` — for resume (continuing human review)

### 5.2 Core of run handling

```python
emitter = WSEventEmitter(ws, run_id, history)          # events → WS stream + workspace save hook
await ws.send_json({"kind": "run_started", "runId": run_id})

graph = dispatch_graph(arch, model_cfg, emitter, run_id)   # pass the whole architecture dict
active_runs[run_id] = graph

state0 = initial_state(task=..., task_tags=..., batch_mode=False, intent=..., criteria=...)
config = {"configurable": {"thread_id": run_id},        # MemorySaver thread key
          "recursion_limit": cfg.MAX_RETRIES * 10 + 20}
final = await graph.ainvoke(state0, config=config)

await ws.send_json({"kind": "run_complete", "runId": run_id,
                    "result": {"answer": final.get("answer"),
                               "reviewDelta": final.get("review_delta"),
                               "reviewBranch": final.get("review_branch")}})
```

Errors distinguish `ValueError` (e.g. an architecture that cannot compile) from generic `Exception`, and are sent as `{"kind": "error"}`.
Failures inside nodes flow into the `event` stream via `make_error_event` (AGENTS.md §7).

### 5.3 Workspace persistence (`server/workspace.py`)

When a `node_end` event has `output`, `WSEventEmitter.__call__` (`events.py`) calls
`write_node_output(run_id, node_id, output)`, which saves it as `server/workspace/<run_id>/<seq>-<node_id>.md`
(seq is 3 digits, to handle re-runs of the same node). Graph/node code knows nothing about saving (separation of
concerns) — the harness's `ListEventEmitter` does not save.

- `_extract_body` extracts the main body from the output (`answer`/`plan`/`reasoning`/`summary`/`result`) and
  writes it as the Markdown body; the remaining metadata is appended as a ```json code block.
- Reading is via §4's `GET /api/runs/{run_id}/files` (+`/{name}`) — `read_run_file` guards against path traversal.
- Frontend: `ui/src/types/workspace.ts` (Zod) + `ui/src/registry/loadRunFiles.ts` (fetch, `VITE_API_BASE`) +
  `ui/src/panels/Markdown.tsx` (react-markdown + remark-gfm). A react-query-based file viewer in LogPanel,
  and inline Markdown rendering in the Inspector output area.
- Tests: 10 in `server/tests/test_workspace.py`.

---

## 6. Nodes = helpers called by graphs (not NodeBase)

Because the execution engine is LangGraph, nodes are not abstract classes but **async functions registered on a `StateGraph`**.
Shared logic is factored into helpers in `server/nodes/`.

### 6.1 `run_llm_step` (`nodes/llm_step.py`)

Shared helper for structured-output LLM calls. Collects input keys from `AgentState` to build the prompt,
and calls `model.with_structured_output(output_model)`. After one recovery retry, emits `make_error_event` on failure.

```python
result = await run_llm_step(
    state, node_id="reasoning",
    system_prompt=REASONING_SYSTEM_PROMPT,
    input_keys=[("task", "Task"), ("plan", "Plan"), ("feedback", "Previous Feedback")],
    output_model=ReasonOut,           # Pydantic: {answer: str, confidence: float}
    model=model, emit=emit, run_id=run_id,
)
```

### 6.2 `make_human_checkpoint` (`nodes/checkpoint.py`)

Based on LangGraph `interrupt()`. Emits an `interrupt` event and pauses the graph.
The `decision` the frontend sends via `resume` becomes the return value of `interrupt()`, and depending on `action`
it branches with `Command(goto=..., update=...)` (`revise` → re-enter `reasoning`, `approve`/`reject` → `output`).

### 6.3 `make_review` (`nodes/review.py`) — intent×criteria review

A review node factory that replaces confidence self-scoring routing (Policy redesign Phase 1, `POLICY_REDESIGN.md`).
With an independent-verifier prompt, it checks the answer against intent and criteria and produces a `ReviewDelta`
(`models.py`: `per_criterion` (met/unmet/unsure) / `misalignments` / `elicit_questions` / `proposed_criteria` /
`reroute_hint` — **no score**). It merges seed criteria (node config) with the criteria in state, and
finalizes the branch (`accept`/`refine`/`clarify`) in the node, storing it in `state["review_branch"]`.
On `refine`, it passes only the unmet deltas as feedback and increments `retries`; batch demotion is emitted
as a `policy_decision` event. `ReasonOut.confidence` remains only as a reference metric (not used for routing).

### 6.4 `policy.py` — pure routing functions

`compute_review_branch(state, ...)` decides `accept`/`refine`/`clarify` from the `ReviewDelta` contents alone:
must_pass unmet → `refine` (`clarify` once retries are exhausted), unsure/misalignment/elicit questions → `clarify`,
all met → `accept`. A match on `ESCALATE_TAGS` forbids accept (→ clarify), and in `batch_mode` clarify is demoted to accept.
`make_route_review(wired)` builds a sync router for LangGraph `add_conditional_edges`; it does not recompute, it only
reads the decision stored in `state["review_branch"]`. When `wired` (the set of connected sourceHandles) is given, it
falls back from unconnected branches in a conservative order (clarify > refine > accept) — used by canvas compilation (§7.4).
Emitting is done on the graph node side.

> **Steps to add a new node**: ① write a helper function in `nodes/` → ② `add_node`/wire edges in a builder under `graphs/` →
> ③ add a manifest dict to `BUILTIN_MANIFESTS` in `manifests.py` → ④ check the impact on frontend Zod schemas.

---

## 7. Execution engine = LangGraph StateGraph (`server/graphs/`)

There is no `ExecutionEngine`/topological sort. Each architecture is one `StateGraph` builder function.
Shared state is `AgentState` (TypedDict) in `state.py`; the checkpointer is `MemorySaver`.

### 7.1 Dispatch (`main.py: dispatch_graph`)

```python
def dispatch_graph(architecture, model_cfg, emit, run_id):
    arch_name = (architecture.get("metadata") or {}).get("name", "")
    cfg = {**DEFAULT_MODEL_CFG, **model_cfg}
    if arch_name == "gsm8k-baseline":  return build_baseline(model, emit, run_id)
    if arch_name == "gsm8k-treatment": return build_treatment(model, emit, run_id)
    return compile_graph(architecture, cfg, emit, run_id)   # v0.3: canvas graph fallback (§7.4)
```

### 7.2 baseline (`graphs/baseline.py`)

```
reasoning → output → END
```
Single-shot reasoning with no verification. The Baseline side of the v0.1 validation strategy (`v0.1-validation.md`).

### 7.3 treatment (`graphs/treatment.py`)

```
planning → reasoning → review (intent×criteria check, ReviewDelta)
                          ├─(accept)  → output
                          ├─(refine)  → reasoning (feedback with unmet deltas only)
                          └─(clarify) → human_checkpoint ─(approve/reject)→ output
                                                          └(revise)────────→ reasoning
output → END
```

Conditional branching is `add_conditional_edges("review", route_review, {...})` — the router reads the decision the
review node stored in `state["review_branch"]` (§6.4). The retry limit is controlled by `max_retries` + `recursion_limit`.
The Treatment side = proving that "structure raises pass@1 for the same model".

### 7.4 compile_graph — dynamic compilation of canvas graphs (`graphs/compile.py`, v0.3)

`compile_graph(architecture, default_model_cfg, emit, run_id)` turns an Architecture (dict) serialized from the
canvas into an executable `CompiledGraph`. Node mapping:

| manifest type | Compiled result |
|---------------|-----------------|
| `io.input` / `io.output` / `model.binding` | passthrough node (`PASSTHROUGH_TYPES`) — io.input prefers the submitted task and injects `config.sample` as a fallback only when it is empty; io.output emits an answer/review summary |
| `runtime == "llm_step"` (`planning.decompose`/`reasoning.cot`) | builds a `run_llm_step` node from the `LLM_STEP_TABLE` spec (output_model · state update mapping) |
| `review.intent` | reuses `make_review` — applies the node config's `criteria`/`maxRetries`/`escalateTags` |
| `human.checkpoint` | `make_human_checkpoint` + routes based on outgoing handles |
| `loop.guard` | `_make_loop_guard_node` — self-routing via `Command(goto=...)` (§7.4a) |

Edges are wired automatically from `architecture.edges`: nodes with no incoming edges → `START`, nodes with no outgoing edges → `END`.
`review.intent` uses `add_conditional_edges` + `make_route_review(wired)` — routes only to connected handles, with
a conservative fallback for unconnected branches (clarify > refine > accept). The checkpointer is `MemorySaver`.
`_filter_control_edges` prevents targets from firing twice due to io.input fan-out
(it removes io.input edges to targets that already have a real upstream processing node).

**Limitations (2026-07-03)**: llm_step only supports types registered in `LLM_STEP_TABLE` (unregistered types raise `ValueError`),
and only `modelSlots[0]` is resolved for the model. There are dedicated unit tests (`server/tests/test_compile.py`) and a
starter-graph WebSocket integration test (`server/tests/test_ws_starter_graph.py`).

#### 7.4a `loop.guard` — first-class loop control node (2026-08-07, commits `0d3f73e`–`b3c86ca`)

`loop.guard` is a first-class canvas node that replaces the sidecar `LoopPolicy` (2026-08-06 design, superseded).
It has one `Feedback` input and two outputs, `Loop back`/`Exit`, and its config consists of a five-axis guard
(`maxIterations`/`maxTokens`/`maxCostUsd`/`maxDurationSec`/`stuckWindow`+`stuckThreshold`) and the behavior on
exhaustion (`onExhaustion`: `exit`/`escalate`/`fail`). Like `human.checkpoint`, it routes itself with
`Command(goto=...)` instead of plain edge wiring, reading the re-entry/exit targets directly from the `loopBack`/`exit`
outgoing edges (`_handle_targets`) — each port must have exactly one outgoing edge, otherwise it is a compile error.
The compiler finds cycles in the graph with Tarjan SCC (`_tarjan_scc`), but first prunes the outgoing edges of every
`loop.guard` node; if any component of size 2 or more remains (`_validate_gated_cycles`), it raises `ValueError` —
**a feedback cycle drawn without a guard is now a compile error** (previously it silently ran with the risk of an
infinite loop). The loop body that token/cost budgets are attributed to is not user-declared; it is derived from graph
reachability as the set of nodes reachable from the `loopBack` target (`_derive_loop_members`). Detailed design:
`docs/superpowers/specs/2026-08-07-loop-node-design.md`.

---

## 8. Frontend connection — just one line (`ui/src/transport/TransportContext.tsx`)

```ts
function createTransport(): Transport {
  const wsUrl = import.meta.env.VITE_WS_URL   // real server if set, Mock otherwise
  return wsUrl ? new WebSocketTransport(wsUrl) : new MockTransport()
}
```

To connect to the backend, set `VITE_WS_URL=ws://localhost:8000/ws/run` in `ui/.env`. No code changes.

### CORS

`server.cors_origins` in `config.yaml` (default `http://localhost:5137`) is passed to the `CORSMiddleware` in `main.py`.

---

## 9. Implementation status by phase (synced with ROADMAP)

| Phase | Scope | Status |
|-------|-------|--------|
| v0.1 | `/api/nodes`, `ws/run` (run), LangGraph baseline/treatment, node highlighting | ✅ (only manual E2E verification remains) |
| v0.2 | Governance/ruff/tests, error and logging standardization, documentation consistency | ✅ |
| v0.3 | **Dynamic compilation of canvas graphs** (`compile_graph`, §7.4) + workspace persistence (§5.3) + review/policy redesign Phase 1 (§6.3–6.4) | 🟡 core implemented (E2E verification and `test_compile.py` remaining) |
| v0.4+ | GSM8K batch runs (Baseline vs Treatment pass@1), Human Checkpoint frontend UI, architecture save UI | ⬜ |

Test status (2026-07-03): 35 backend pytest tests (events 3 · graph_baseline 1 · graph_treatment 2 ·
harness 2 · manifests 3 · policy 14 · workspace 10), 7 frontend vitest tests (LogPanel 1 · eventReducer 2 · events.schema 4).

---

## 10. Frontend handling by event type

| eventType | Frontend handling (`eventReducer`/`TransportContext`) |
|-----------|-------------------------------------------------------|
| `node_start` | Set the node's status → `running`, update `activeNodeId` |
| `node_end` | status → `success`, accumulate output/metrics |
| `error` | status → `failed`, show `error.detail` in LogPanel/Inspector |
| `interrupt` | (planned for v0.4) show Human Checkpoint UI → user decision → send `resume` |
| `decision_record` | Record the human decision log |
| `run_complete` / `run_started` / `error` (kind) | Update the run status banner via `setRunState` |

---

## 11. Development environment

```bash
# Combined run (backend + frontend)
./start.sh

# Individually
cd server && ../.venv/bin/uvicorn main:app --reload --port 8000
cd ui && npm run dev -- --port 5137
```

API keys go in `server/.env` (`ANTHROPIC_API_KEY`, etc.). Everything else is in `config.yaml`.

---

## 12. v0.3 — dynamic compilation of canvas graphs (implemented, commit `faa736e`)

`dispatch_graph` falls back to **`compile_graph(architecture, ...)`** (§7.4) for architectures other than the fixed
arch names. The canvas-serialized graph sent by the frontend Toolbar's `current canvas` option runs as-is.

```
Architecture.nodes / edges
        ↓
compile_graph: manifest type → node factory mapping, edges → StateGraph edges (automatic START/END wiring)
        ↓
review.intent → add_conditional_edges(route_review(wired)),  human.checkpoint → interrupt
        ↓
StateGraph.compile(checkpointer=MemorySaver()).ainvoke(state0)
        ↓
ExecutionEvent → WSEventEmitter → WS  (the upstream ws_run handler is unchanged)
```

The `dispatch_graph` signature was kept (first argument extended from arch name → architecture dict), and only the
engine was extended while the WS handler stayed as-is. Node ids in `starterArchitecture.ts` are aligned with the
treatment graph's node names, which keeps the mapping simple.

**Remaining**: E2E verification (`current canvas` Run — on hold due to `ANTHROPIC_API_KEY` 401),
dedicated unit tests for `compile.py`, extending `LLM_STEP_TABLE` (arbitrary llm_step types), and resolving beyond `modelSlots[0]`.
