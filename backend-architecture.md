# Agentforge — Backend Architecture

> Status: living doc — **a description of the current code** (2026-11-01), not the target design.
> [DIRECTION.md](./DIRECTION.md) takes precedence for direction and the roadmap.
> Related: [CLAUDE.md](./CLAUDE.md) · [AGENTS.md](./AGENTS.md) · [skills/agentforge/SKILL.md](./skills/agentforge/SKILL.md)

The backend turns an `arch.yaml` into a LangGraph `StateGraph` and runs it. Two front doors share
one core: the headless CLI (`server/cli.py`, the main path, driven from Claude Code) and the
FastAPI server (`server/main.py`, used by the optional browser dashboard).

---

## 1. Tech stack

| Area | Used |
|------|------|
| Execution engine | **LangGraph** (`StateGraph`, `interrupt`/`Command`, `AsyncSqliteSaver`) |
| LLM adapters | LangChain (`langchain-anthropic`, `langchain-openai`, `langchain-google-genai`; OpenRouter via the OpenAI adapter) |
| Types/validation | Pydantic v2 (structured LLM output) |
| Web | FastAPI + uvicorn (dashboard only) |
| Config | PyYAML (`config.yaml`) + python-dotenv (`server/.env` API keys) |
| Packaging | `uv` (Python 3.12, `server/.venv`) |

---

## 2. Pipeline: YAML → graph → run

```
server/arch/*.yaml
   │ archfile.parse_arch(text, default_model)      → (Architecture dict, warnings)
   ▼
Architecture {metadata, flow, nodes, edges}
   │ graphs.compile_graph(arch, model_cfg, emit, run_id, checkpointer)
   ▼
CompiledGraph ── ainvoke ──► node functions ── emit(ExecutionEvent) ──► emitter
                                                                  ├─ FileEventEmitter (CLI)
                                                                  └─ WSEventEmitter (server)
```

### 2.1 `archfile.py` — parse

- `flow:` is plain mermaid (`a --> b`, `a -->|label| b`). `parse_flow` reads it; errors are
  `ArchError` with the line number in the original YAML file.
- Every node under `nodes:` becomes a `custom.node` (runtime `llm_step`) with `in`/`out` ports,
  `prompt`, and an inline model slot (`model`, `temperature`, `max_tokens`).
- `run: human.checkpoint` / `run: loop.guard` select a built-in instead. `input` and `output`
  map to `io.input` / `io.output`.
- Validation: a node with 2+ labelled outgoing edges is a branch node (`_validate_branch_capable`);
  a node with 2+ plain incoming edges needs `join: all|any` (`_validate_fan_in`, stored as
  `joinMode` `and`/`or`); every `in` key must be produced upstream or preseeded (`task`, …).
- Cycles: `_back_edges` finds them and `_insert_guards` inserts a `loop.guard` where the author
  did not write one.
- The original `flow` string is kept on the Architecture so the dashboard can render it.

### 2.2 `graphs/compile.py` — compile

Node types (`server/manifests.py`, `BUILTIN_MANIFESTS`) and how they compile:

| Type | Runtime | Compiled as |
|------|---------|-------------|
| `io.input` / `io.output` | `io` | passthrough nodes (`PASSTHROUGH_TYPES`) |
| `custom.node` | `llm_step` | `run_llm_step` with an output model built from the node's `out` ports; a branch node also gets a `route` field limited to its labels (`_make_router`) |
| `human.checkpoint` | `checkpoint` | `make_human_checkpoint` — `interrupt()`, then `Command(goto=…)` to the wired label |
| `agent.node` (`run: agent`) | `agent` | `nodes/agent_step.make_agent_node` — mini-swe-agent loop over the run's `files/` |
| `loop.guard` | `loop_guard` | `_make_loop_guard_node` — `loopBack`/`exit` self-routing with iteration/token/cost/time/stuck limits |

Edges: nodes with no incoming edges hang off `START`, nodes with no outgoing edges go to `END`.
Fan-in follows `joinMode` (`_build_plain_edge_plan`). A cycle without a `loop.guard` is a compile
error (`_tarjan_scc` + `_validate_gated_cycles`). The checkpointer is passed in by the caller.

### 2.3 `nodes/` — runtime helpers

- `llm_step.run_llm_step` — builds the prompt from the node's `in` keys, calls
  `model.with_structured_output(...)`, retries once, and emits a `log` event with `token_usage`
  (`prompt`, `completion`, `total_tokens`, `cost`, `model`). Cost is what the provider reported
  for the call when it reports one (OpenRouter does, read by `UsageCostHandler`), otherwise
  `config.yaml models.pricing` via `models.cost_for_usage`. With neither, `cost` is `null` — never
  a silent `0.0` — and the CLI prints `$?` plus `cost unknown (no price for <model>)`.
- `agent_step.make_agent_node` — runs mini-swe-agent's `DefaultAgent` in a thread. The model is
  our LangChain model behind a small adapter (`_ChatModel`), so agent nodes share providers, keys,
  and cost records with llm nodes; litellm is installed with mini-swe-agent but never called.
  Each bash command runs in bwrap (`bwrap_args`): `--clearenv`, `--unshare-all` (plus
  `--share-net` when `network: true`), read-only `/usr` and `/etc`, tmpfs `/tmp`, and only the
  run's `files/` writable. `secrets:` names are copied from the server environment; tools from
  `server/agent_tools/` (and `obscura` if installed) are mounted at `/opt/agentforge/bin`. `pick_tools` narrows that set to the node's `tools:` list (system commands under /usr map to `None` and are not mounted).
  `files/` is a git repo (`gitfiles.py`) and every visit ends in a commit; the node output carries
  `changedFiles`, `commit`, `steps`, and the trajectory path (`agent/<node>-<n>.json`). Hitting
  `limits` (`steps` 30, `cost` 0.50 by default) fails the node after committing its work.
  With a `files:` scope, `files_mounts` puts a tmpfs over `files/` and mounts only the listed
  folders on top (`.git` only visible when `.` is listed, and an unscoped or `.` node gets it
  read-only). Before every command the folders are opened by fd from `files/` without following
  symlinks (a symlink fails the node) and bound with `--bind-fd`/`--ro-bind-fd`; because bwrap
  0.9 turns those fds back into paths before mounting, `mount_check` re-checks each mount's
  device:inode inside the sandbox before the command runs. Write folders, and read folders nested
  under one, are created up front with `mkdir` relative to the parent fd. `SandboxEnvironment` (a
  `BubblewrapEnvironment` subclass) runs commands without mini's extra `--bind cwd cwd`, which
  would hide those mounts.
  `limits.memory_mb` / `cpu_seconds` become a `ulimit_prefix` (`ulimit -v`, `ulimit -t`) put in
  front of every command (failing the command if a limit cannot be set); each process the command
  starts gets its own cap.
- `checkpoint.make_human_checkpoint` — emits an `interrupt` event whose payload lists the wired
  labels, then pauses.
- `loop_guard.py` — pure guard evaluation used by the `loop.guard` node.

---

## 3. `runner.py` — shared run core

| Function | Does |
|----------|------|
| `open_checkpointer()` | Opens `AsyncSqliteSaver` at `server/workspace/checkpoints.sqlite` (one file for CLI and server) |
| `start_run(arch, run_id, task, model_cfg, emit, checkpointer, …)` | Writes `run.json`, compiles, runs with `thread_id = run_id` |
| `resume_run(run_id, decision, emit, checkpointer)` | Recompiles from the architecture saved in `run.json` (not the current file) and resumes with `Command(resume=decision)` |
| `replay_run(parent_id, arch, run_id, from_node, emit, checkpointer, …)` | Forks the parent's checkpoint taken just before the start node into a new thread and continues with the edited architecture |

Each returns a `RunOutcome(run_id, status, final, error)` with `status` `done` / `paused` / `error`,
and updates `run.json` to match.

### 3.1 Replay (`replay.py`)

- `changed_nodes` compares old and new architectures. Any change to the flow (node set, types,
  `joinMode`, edges, or built-in node settings) raises `ReplayError("flow changed — run it fresh")`.
  Only `custom.node` specs (prompt, ports, model, temperature, …) may change.
- `pick_from` chooses the start node: the first changed node in the parent's first-visit order
  (from `events.jsonl`), or `--from`. If a node visited before it changed, it refuses with
  `upstream node '…' changed — replay from '…' instead`.
- The fork starts at the **first visit** of the start node, so loop counters and feedback reset.
- `run.json` records `parent {runId, checkpointId}`, `fromNode`, `reused` nodes, and `savedCost`.
- Agent nodes (`agent.node`) may change like `custom.node`. `files/` forks too (`_fork_files`):
  it starts at the last agent `commit` in the parent's events before the start node
  (`commit_before`), else at the parent's `filesStart`, else its root commit. Without `--repo` the
  parent's repo is cloned and reset to that commit (`gitfiles.clone_at`); with `--repo` a new
  worktree branch `agentforge/<run_id>` starts there and keeps the parent's `base` for the
  diffstat. `run.json` records `filesStart`.

---

## 4. Run records (`workspace.py`)

Everything for a run lives in `server/workspace/<run_id>/`:

| File | Written by | Contents |
|------|-----------|----------|
| `run.json` | `write_run_record` / `update_run_record` | arch path and text, Architecture, model config, task, status, error, replay lineage |
| `events.jsonl` | `persist_event` (both emitters) | every `ExecutionEvent`, one per line |
| `<seq>-<node_id>.md` | `write_node_output` | each `node_end` output as Markdown (main body + JSON metadata) |

Run ids are validated (`_check_run_id`) and file reads guard against path traversal.

---

## 5. CLI (`cli.py`)

Invoked as `agentforge <command>` through the repo-root `agentforge` wrapper (no args or `serve`
starts the dev servers instead).

| Command | Exit codes |
|---------|-----------|
| `check <arch.yaml> [--model p/m]` | 0 ok / 1 error — parse + compile only, no LLM calls |
| `run <arch.yaml> --task "…" [--model p/m] [--repo <path>] [--json]` | 0 done / 3 paused / 1 error |
| `resume <run_id> --choice <label> [--note "…"] [--json]` | same as `run` |
| `replay <run_id> [--arch edited.yaml [--model p/m]] [--from <node>] [--json]` | same as `run` |
| `show <run_id> [<node>]` | 0 / 1 — the summary, or one node's full output |
| `eval <arch.yaml> [--limit N] [--checkpoint <label>] [--model p/m] [--json]` | 0 / 1 — runs the `eval:` dataset and prints the report (`evaluate.py`) |
| `compare <a.yaml> [<b.yaml>] [--set node.field=value]… [--limit N] [--checkpoint <label>] [--json]` | 0 / 1 — evals both variants on A's dataset and prints them side by side |

`eval` runs each dataset item (× `repeat`) as a normal run via `runner.start_run`, answers
checkpoints only when `--checkpoint` names a wired label (otherwise the run ends `paused` and
counts as a failure), grades the final answer (`number` | `exact` | `contains` | `llm`), and
reports success rate, cost per success, error rate, per-node average tokens/cost, and branch-label
counts. `check` also validates an `eval:` block when present.

`compare` builds variant B from a second file and/or `--set` edits applied to the YAML
(`apply_sets`), runs both through `run_eval` on the same items, pairs results per run, and flags
the success-rate difference as noise when an exact sign test on the discordant pairs gives
p ≥ 0.05 (`paired_p`).

`run --repo <path>` (needs an agent node) makes the run's `files/` a git worktree of that repo on
a new branch `agentforge/<run_id>` from `HEAD` (`runner._open_worktree`); `run.json` records
`repo {path, branch, base}`. The sandbox mounts the repo's git dir read-only so `git` works
inside. When the run ends (not paused) `_close_worktree` removes the worktree, keeps the branch,
and stores its `diffstat`, which the summary prints.

Output is one short line per node visit (status, tokens, cost, a snippet) plus a total, to keep
what Claude reads back small. `--json` prints the same data as JSON.

---

## 6. Server (`main.py`)

The lifespan opens the shared SQLite checkpointer, so paused runs survive a server restart.

### 6.1 REST

| Endpoint | Description |
|----------|-------------|
| `GET /api/arch`, `GET /api/arch/{name}` | List / parse `server/arch/*.yaml` (`arch_files.py`) |
| `GET /api/models` | Enabled models from `config.yaml`; `available` shows whether the provider key is set |
| `GET /api/nodes` | `BUILTIN_MANIFESTS` |
| `GET /api/runs/{run_id}/files`, `…/files/{name}` | Workspace file list / content |
| `GET /api/openrouter/catalog`, `GET /api/openrouter/favorites` | OpenRouter model catalog and local favorites |
| `GET|POST /api/architectures`, `GET /api/architectures/{id}` | Legacy canvas-JSON storage, unused by the dashboard |

### 6.2 WebSocket `ws://…/ws/run`

Frontend → backend (`kind`):

```jsonc
{ "kind": "run", "archFile": "gsm8k.yaml", "input": { "task": "…" }, "model": { "provider": "…", "model": "…" } }
{ "kind": "resume", "runId": "…", "decision": { "action": "<label>", "reason": "" } }
{ "kind": "reconnect", "runId": "…" }
```

Backend → frontend (`kind`): `run_started`, `event` (an `ExecutionEvent.to_frontend()`),
`interrupt` (`nodeId`, `payload`), `run_complete` (`result.answer`), `error` (`message`), and
`state` (event snapshot for `reconnect`).

`run` with `archFile` parses the YAML server-side, writes `run.json`, and runs through
`dispatch_graph` → `compile_graph`. `resume` uses the in-memory graph if present, otherwise
falls back to `runner.resume_run` with the persisted record.

### 6.3 Events (`events.py`)

`ExecutionEvent` serializes to camelCase via `to_frontend()`, 1:1 with
`ui/src/types/events.ts`. Main `eventType`s: `node_start`, `node_end`, `log` (token usage),
`interrupt`, `decision_record`, `error` (built by `make_error_event`, with `error = {type, detail}`).
Emitters: `WSEventEmitter` (WS + files), `FileEventEmitter` (files only, CLI),
`ListEventEmitter` (memory only: `check`, eval, tests).

---

## 7. Configuration

- `config.yaml` — server/CORS, model list and defaults, `models.pricing`, run parameters
  (`max_retries`, thresholds).
- `server/.env` — provider API keys (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`,
  `OPENROUTER_API_KEY`, `LOCAL_BASE_URL`). Copy from `server/.env.example`.
- The default model when neither the YAML nor `--model` sets one is `runner.DEFAULT_MODEL_CFG`.
